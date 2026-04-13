import atexit
import datetime
import os
import subprocess
import threading
import time


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == '':
        return int(default)
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


def _env_list(name, default_items):
    raw = (os.getenv(name) or '').strip()
    if not raw:
        return list(default_items)
    items = [item.strip() for item in raw.split(',') if item.strip()]
    return items or list(default_items)


class _NoopGPIO:
    BCM = 'BCM'
    OUT = 'OUT'
    HIGH = 1
    LOW = 0

    def setmode(self, *_args, **_kwargs):
        return None

    def setup(self, *_args, **_kwargs):
        return None

    def output(self, *_args, **_kwargs):
        return None

    def input(self, *_args, **_kwargs):
        return 0

    def cleanup(self):
        return None


class EventLedController:
    """
    GPIO LED state controller bound to current backend event workflow.

    States:
      READY       -> green blinking, red off
      RUNNING     -> green solid on, red off
      COMPLETED   -> green blinking, red off
      INTERRUPTED -> green off, red on
    """

    def __init__(self, app):
        self.app = app
        self.enabled = _env_bool('LED_MONITOR_ENABLED', default=True)
        self.green_pin = _env_int('GREEN_LED_GPIO', 4)
        self.red_pin = _env_int('RED_LED_GPIO', 18)
        self.poll_interval_sec = max(1, _env_int('LED_POLL_INTERVAL_SEC', 2))
        self.required_services = _env_list(
            'LED_REQUIRED_SERVICES',
            ['visitor-backend', 'nginx', 'hostapd', 'dnsmasq'],
        )
        self.camera_health_enabled = _env_bool('LED_CAMERA_HEALTH_EXCEPTIONS_ENABLED', default=True)
        self.camera_stale_sec = max(3, _env_int('LED_CAMERA_STALE_SEC', 8))
        self.camera_error_tokens = [
            tok.lower() for tok in _env_list(
                'LED_CAMERA_ERROR_TOKENS',
                [
                    'camera not found',
                    'could not open camera stream',
                    'failed to read camera frame',
                    'processing error',
                    'camera disconnected',
                    'device not found',
                    'no such file',
                    'input/output error',
                ],
            )
        ]

        self._lock = threading.Lock()
        self._blink_thread = None
        self._blink_flag = False
        self._monitor_thread = None
        self._stop_event = threading.Event()
        # Start unset so the first computed state always applies LED outputs.
        self._state = None
        self._gpio_ready = False
        self._GPIO = _NoopGPIO()
        self._last_interrupt_reason = ''
        self._last_logged_interrupt_reason = ''

    def start(self):
        if not self.enabled:
            self.app.logger.info("LED monitor disabled (LED_MONITOR_ENABLED=0)")
            return

        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        if not self._init_gpio():
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name='event-led-monitor',
            daemon=True,
        )
        self._monitor_thread.start()
        atexit.register(self.shutdown)
        self.app.logger.info(
            "LED monitor started (green_pin=%s, red_pin=%s)",
            self.green_pin,
            self.red_pin,
        )

    def shutdown(self):
        self._stop_event.set()
        with self._lock:
            self._blink_flag = False
        try:
            self._GPIO.cleanup()
        except Exception:
            pass

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO  # type: ignore
            self._GPIO = GPIO
            self._GPIO.setmode(self._GPIO.BCM)
            self._GPIO.setup(self.green_pin, self._GPIO.OUT)
            self._GPIO.setup(self.red_pin, self._GPIO.OUT)
            self._gpio_ready = True
            # Initial indicator while monitor determines exact state.
            self._GPIO.output(self.green_pin, self._GPIO.HIGH)
            self._GPIO.output(self.red_pin, self._GPIO.LOW)
            return True
        except Exception as exc:
            self._gpio_ready = False
            self.app.logger.warning("LED monitor disabled: GPIO init failed: %s", exc)
            return False

    def _is_service_active(self, name):
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', name],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip() == 'active'
        except Exception:
            return False

    def _system_not_ready_reason(self):
        for svc in self.required_services:
            if not self._is_service_active(svc):
                return f"Required service '{svc}' is not active"
        return ''

    def _runtime_camera_health_issue(self, snapshot):
        if not self.camera_health_enabled:
            return ''

        status = str(snapshot.get('status') or '').strip().lower()
        workflow_active = bool(snapshot.get('workflow_active'))
        if not (workflow_active or status == 'active'):
            return ''

        selected_camera_id = str(snapshot.get('selected_camera_id') or '').strip()
        if not selected_camera_id:
            return 'Event is active but no camera is selected'

        try:
            from models.camera import Camera

            cam = Camera.query.filter_by(camera_id=selected_camera_id).first()
            if cam is None:
                return f"Selected camera '{selected_camera_id}' not found in database"
            if not bool(getattr(cam, 'is_active', True)):
                return f"Selected camera '{selected_camera_id}' is inactive"
        except Exception as exc:
            # DB/read failures should be considered an interruption for LED safety.
            return f"Failed to validate selected camera '{selected_camera_id}': {exc}"

        try:
            from routes.camera import _RUNTIME_LOCK, _RUNTIME_STATS, _default_runtime

            with _RUNTIME_LOCK:
                runtime = dict(_RUNTIME_STATS.get(selected_camera_id, _default_runtime(selected_camera_id)))
        except Exception as exc:
            return f"Failed to read runtime stats for '{selected_camera_id}': {exc}"

        camera_online = runtime.get('camera_online')
        if camera_online is False:
            return f"Camera '{selected_camera_id}' is offline/disconnected"

        last_error = str(runtime.get('last_error') or '').strip()
        if last_error:
            lowered = last_error.lower()
            if any(token and token in lowered for token in self.camera_error_tokens):
                return f"Camera '{selected_camera_id}' runtime error: {last_error}"

        last_frame_raw = runtime.get('last_frame_at')
        if not last_frame_raw:
            return f"Camera '{selected_camera_id}' has not produced frames yet"

        try:
            last_frame_dt = datetime.datetime.fromisoformat(str(last_frame_raw))
            age_sec = (datetime.datetime.utcnow() - last_frame_dt).total_seconds()
            if age_sec > float(self.camera_stale_sec):
                return (
                    f"Camera '{selected_camera_id}' frame stream is stale "
                    f"({age_sec:.1f}s > {self.camera_stale_sec}s)"
                )
        except Exception:
            # Invalid timestamp indicates broken runtime telemetry.
            return f"Camera '{selected_camera_id}' has invalid frame timestamp"

        return ''

    def _blink_green_loop(self):
        while not self._stop_event.is_set():
            with self._lock:
                if not self._blink_flag:
                    break
            try:
                current = int(self._GPIO.input(self.green_pin))
                self._GPIO.output(self.green_pin, self._GPIO.LOW if current else self._GPIO.HIGH)
            except Exception:
                pass
            time.sleep(1)

    def _start_blinking(self):
        with self._lock:
            if self._blink_thread and self._blink_thread.is_alive():
                return
            self._blink_flag = True
            self._blink_thread = threading.Thread(
                target=self._blink_green_loop,
                name='event-led-blink',
                daemon=True,
            )
            self._blink_thread.start()

    def _stop_blinking(self):
        with self._lock:
            self._blink_flag = False
        try:
            self._GPIO.output(self.green_pin, self._GPIO.HIGH)
        except Exception:
            pass

    def _set_state(self, new_state):
        if new_state == self._state:
            return
        self._state = new_state
        self.app.logger.info("LED state -> %s", new_state)

        if new_state == 'READY':
            try:
                self._GPIO.output(self.red_pin, self._GPIO.LOW)
            except Exception:
                pass
            self._start_blinking()
            return

        # Non-ready states should stop blinking first.
        self._stop_blinking()

        if new_state == 'RUNNING':
            try:
                self._GPIO.output(self.green_pin, self._GPIO.HIGH)
                self._GPIO.output(self.red_pin, self._GPIO.LOW)
            except Exception:
                pass
            return

        if new_state == 'COMPLETED':
            try:
                self._GPIO.output(self.red_pin, self._GPIO.LOW)
            except Exception:
                pass
            self._start_blinking()
            return

        # INTERRUPTED fallback
        try:
            self._GPIO.output(self.green_pin, self._GPIO.LOW)
            self._GPIO.output(self.red_pin, self._GPIO.HIGH)
        except Exception:
            pass

    def _desired_state(self):
        system_reason = self._system_not_ready_reason()
        if system_reason:
            self._last_interrupt_reason = system_reason
            return 'INTERRUPTED'

        try:
            from routes.events import get_event_state_snapshot
            snapshot = get_event_state_snapshot(sync=True) or {}
        except Exception as exc:
            self._last_interrupt_reason = f"Failed to read event state: {exc}"
            return 'INTERRUPTED'

        camera_reason = self._runtime_camera_health_issue(snapshot)
        if camera_reason:
            self._last_interrupt_reason = camera_reason
            return 'INTERRUPTED'

        status = str(snapshot.get('status') or '').strip().lower()
        workflow_active = bool(snapshot.get('workflow_active'))
        self._last_interrupt_reason = ''

        # Requested behavior:
        # - READY (wifi/ap on) => blink green
        # - Event scheduled/active => constant green
        # - Event completed/over => blink green
        if workflow_active or status in ('scheduled', 'active'):
            return 'RUNNING'
        if status == 'completed':
            return 'COMPLETED'
        return 'READY'

    def _monitor_loop(self):
        if not self._gpio_ready:
            return
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    next_state = self._desired_state()
                    if (
                        next_state == 'INTERRUPTED'
                        and self._last_interrupt_reason
                        and self._last_interrupt_reason != self._last_logged_interrupt_reason
                    ):
                        self.app.logger.warning("LED interrupted: %s", self._last_interrupt_reason)
                        self._last_logged_interrupt_reason = self._last_interrupt_reason
                    elif next_state != 'INTERRUPTED':
                        self._last_logged_interrupt_reason = ''
                    self._set_state(next_state)
            except Exception as exc:
                self.app.logger.warning("LED monitor loop error: %s", exc)
            self._stop_event.wait(self.poll_interval_sec)


_LED_MONITOR = None
_LED_MONITOR_LOCK = threading.Lock()


def start_led_monitor(app):
    global _LED_MONITOR
    with _LED_MONITOR_LOCK:
        if _LED_MONITOR is None:
            _LED_MONITOR = EventLedController(app)
        _LED_MONITOR.start()
        return _LED_MONITOR
