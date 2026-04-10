import atexit
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

        self._lock = threading.Lock()
        self._blink_thread = None
        self._blink_flag = False
        self._monitor_thread = None
        self._stop_event = threading.Event()
        # Start unset so the first computed state always applies LED outputs.
        self._state = None
        self._gpio_ready = False
        self._GPIO = _NoopGPIO()

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

    def _system_ready(self):
        for svc in self.required_services:
            if not self._is_service_active(svc):
                return False
        return True

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
        if not self._system_ready():
            return 'INTERRUPTED'

        try:
            from routes.events import get_event_state_snapshot
            snapshot = get_event_state_snapshot(sync=True) or {}
        except Exception as exc:
            self.app.logger.warning("LED monitor: failed to read event state: %s", exc)
            return 'INTERRUPTED'

        status = str(snapshot.get('status') or '').strip().lower()
        workflow_active = bool(snapshot.get('workflow_active'))

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
