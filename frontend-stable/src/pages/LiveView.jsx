import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';
import { getCurrentEvent } from '../services/eventService';

export default function LiveView() {
  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [streamError, setStreamError] = useState('');
  const [streamNonce, setStreamNonce] = useState(Date.now());
  const [eventInfo, setEventInfo] = useState(null);
  const [liveFps, setLiveFps] = useState(0);
  const [runtimeInfo, setRuntimeInfo] = useState(null);
  const [liveFeedEnabled, setLiveFeedEnabled] = useState(() => {
    try {
      const raw = window.localStorage.getItem('live_feed_enabled');
      if (raw === null) return true;
      return raw !== '0';
    } catch (_) {
      return true;
    }
  });
  const [hasProcessedFrame, setHasProcessedFrame] = useState(false);
  const [deviceError, setDeviceError] = useState('');
  const [isFramePending, setIsFramePending] = useState(false);
  const [cameraFacingMode, setCameraFacingMode] = useState('environment');
  const [backendUnavailable, setBackendUnavailable] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const processedCanvasRef = useRef(null);
  const localStreamRef = useRef(null);
  const avgRttMsRef = useRef(650);
  const fpsWindowRef = useRef({ startMs: 0, frames: 0 });
  const autoRecoverRef = useRef({ lastTs: 0 });

  const clearProcessedFrame = useCallback(() => {
    const outputCanvas = processedCanvasRef.current;
    if (outputCanvas) {
      const outputCtx = outputCanvas.getContext('2d');
      if (outputCtx) {
        outputCtx.clearRect(0, 0, outputCanvas.width, outputCanvas.height);
      }
    }
    fpsWindowRef.current = { startMs: 0, frames: 0 };
    setLiveFps(0);
    setHasProcessedFrame(false);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem('live_feed_enabled', liveFeedEnabled ? '1' : '0');
    } catch (_) {
      // ignore storage errors
    }
  }, [liveFeedEnabled]);

  const stopLocalCamera = useCallback(
    (clearFrame = false) => {
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach((track) => track.stop());
        localStreamRef.current = null;
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
      if (clearFrame) {
        clearProcessedFrame();
      }
    },
    [clearProcessedFrame]
  );

  const fetchCamerasAndEvent = useCallback(async () => {
    try {
      setError('');
      const [cameraRes, eventRes] = await Promise.allSettled([
        api.get('/camera/'),
        getCurrentEvent(),
      ]);
      const list = cameraRes.status === 'fulfilled' && Array.isArray(cameraRes.value?.data)
        ? cameraRes.value.data
        : [];
      setCameras(list);
      const currentEvent = eventRes.status === 'fulfilled' ? (eventRes.value?.data || null) : null;
      setEventInfo(currentEvent);

      if (list.length > 0) {
        const preferredCameraId = currentEvent?.selected_camera_id;
        const preferred = list.find((cam) => cam.camera_id === preferredCameraId);
        if (!selectedCamera || !list.find((cam) => cam.camera_id === selectedCamera.camera_id)) {
          setSelectedCamera(preferred || list[0]);
          setStreamError('');
          setStreamNonce(Date.now());
        } else if (preferred && selectedCamera.camera_id !== preferred.camera_id) {
          setSelectedCamera(preferred);
          setStreamError('');
          setStreamNonce(Date.now());
        }
      }

      if (cameraRes.status === 'rejected') {
        setError('Failed to load camera list. Check backend connection and login token.');
        setBackendUnavailable(true);
      } else {
        setBackendUnavailable(false);
      }
    } catch (_) {
      setError('Failed to load camera list. Check backend connection and login token.');
      setBackendUnavailable(true);
    } finally {
      setLoading(false);
    }
  }, [selectedCamera]);

  useEffect(() => {
    const fetchInitial = async () => {
      try {
        await fetchCamerasAndEvent();
      } finally {
        setLoading(false);
      }
    };
    fetchInitial();
  }, [fetchCamerasAndEvent]);

  useEffect(() => {
    const id = window.setInterval(() => {
      fetchCamerasAndEvent();
    }, 15000);
    return () => window.clearInterval(id);
  }, [fetchCamerasAndEvent]);

  const handleCameraChange = (cameraId) => {
    const camera = cameras.find((c) => c.camera_id === cameraId) || null;
    setSelectedCamera(camera);
    setStreamError('');
    setDeviceError('');
    setRuntimeInfo(null);
    setStreamNonce(Date.now());
  };

  const isClientDeviceMode = useMemo(() => {
    if (!selectedCamera) return false;
    const eventWantsSelectedDeviceCamera =
      eventInfo?.camera_mode === 'default' &&
      (!eventInfo?.selected_camera_id || eventInfo.selected_camera_id === selectedCamera.camera_id);
    return (
      selectedCamera.camera_id === 'EVENT_DEFAULT' ||
      String(selectedCamera.camera_type || '').toLowerCase() === 'browser' ||
      eventWantsSelectedDeviceCamera
    );
  }, [eventInfo?.camera_mode, eventInfo?.selected_camera_id, selectedCamera]);

  const isPhoneClient = useMemo(() => {
    if (typeof navigator === 'undefined') return false;
    const ua = navigator.userAgent || '';
    return /iPhone|Android.+Mobile|Windows Phone|Mobile/i.test(ua);
  }, []);

  const isSelfieMode = cameraFacingMode === 'user';

  useEffect(() => {
    if (!selectedCamera?.camera_id) {
      setRuntimeInfo(null);
      return undefined;
    }
    let cancelled = false;
    const fetchRuntimeStatus = async () => {
      try {
        const res = await api.get('/camera/runtime-status', {
          params: { camera_id: selectedCamera.camera_id },
        });
        if (!cancelled) setRuntimeInfo(res?.data || null);
      } catch (_) {
        if (!cancelled) setRuntimeInfo(null);
      }
    };
    fetchRuntimeStatus();
    const id = window.setInterval(fetchRuntimeStatus, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selectedCamera?.camera_id]);

  useEffect(() => {
    if (!liveFeedEnabled || isClientDeviceMode || !selectedCamera?.camera_id) return;
    const errText = String(runtimeInfo?.last_error || '').toLowerCase();
    if (!errText) return;
    const isOpenError =
      errText.includes('could not open camera stream') ||
      errText.includes('failed to read camera frame') ||
      errText.includes('open exception');
    if (!isOpenError) return;

    const now = Date.now();
    if ((now - Number(autoRecoverRef.current.lastTs || 0)) < 2500) return;
    autoRecoverRef.current.lastTs = now;

    const preferredCameraId = String(eventInfo?.selected_camera_id || '').trim();
    if (preferredCameraId && preferredCameraId !== selectedCamera.camera_id) {
      const preferred = cameras.find((cam) => cam?.camera_id === preferredCameraId);
      if (preferred) {
        setSelectedCamera(preferred);
        setStreamError('');
        setDeviceError('');
        setRuntimeInfo(null);
        setStreamNonce(Date.now());
        fetchCamerasAndEvent();
        return;
      }
    }

    const defaultMode = String(eventInfo?.camera_mode || '').toLowerCase() === 'default';
    if (defaultMode) {
      const fallbackBrowserCamera = cameras.find((cam) => (
        cam?.camera_id === 'EVENT_DEFAULT' ||
        String(cam?.camera_type || '').toLowerCase() === 'browser'
      ));
      if (fallbackBrowserCamera && fallbackBrowserCamera.camera_id !== selectedCamera.camera_id) {
        setSelectedCamera(fallbackBrowserCamera);
        setStreamError('');
        setDeviceError('');
        setRuntimeInfo(null);
        setStreamNonce(Date.now());
        fetchCamerasAndEvent();
        return;
      }
    }

    setStreamError('Camera runtime issue detected. Retrying stream...');
    setStreamNonce(Date.now());
    fetchCamerasAndEvent();
  }, [
    cameras,
    eventInfo?.camera_mode,
    eventInfo?.selected_camera_id,
    fetchCamerasAndEvent,
    isClientDeviceMode,
    liveFeedEnabled,
    runtimeInfo?.last_error,
    selectedCamera?.camera_id,
  ]);

  useEffect(() => {
    if (!liveFeedEnabled) {
      clearProcessedFrame();
      setStreamError('');
      return;
    }
    setStreamNonce(Date.now());
  }, [clearProcessedFrame, liveFeedEnabled]);

  useEffect(() => {
    if (!isClientDeviceMode) {
      stopLocalCamera(true);
      return undefined;
    }

    let cancelled = false;
    let timerId = null;
    let hasRenderedFrame = false;
    let retryDelayMs = isPhoneClient ? 28 : 14;

    const scheduleNext = (delayMs = retryDelayMs) => {
      if (cancelled) return;
      timerId = window.setTimeout(processNextFrame, delayMs);
    };

    const drawProcessedBlob = async (blob) => {
      const outputCanvas = processedCanvasRef.current;
      if (!outputCanvas) return false;
      const outputCtx = outputCanvas.getContext('2d', { alpha: false, desynchronized: true });
      if (!outputCtx) return false;

      const viewportWidth = Math.max(2, outputCanvas.clientWidth || 0);
      const viewportHeight = Math.max(2, outputCanvas.clientHeight || 0);
      if (outputCanvas.width !== viewportWidth) outputCanvas.width = viewportWidth;
      if (outputCanvas.height !== viewportHeight) outputCanvas.height = viewportHeight;

      if (typeof createImageBitmap === 'function') {
        const bitmap = await createImageBitmap(blob);
        const scale = Math.max(viewportWidth / bitmap.width, viewportHeight / bitmap.height);
        const drawWidth = Math.max(1, Math.floor(bitmap.width * scale));
        const drawHeight = Math.max(1, Math.floor(bitmap.height * scale));
        const dx = Math.floor((viewportWidth - drawWidth) / 2);
        const dy = Math.floor((viewportHeight - drawHeight) / 2);
        outputCtx.clearRect(0, 0, viewportWidth, viewportHeight);
        outputCtx.drawImage(bitmap, dx, dy, drawWidth, drawHeight);
        bitmap.close();
        return true;
      }

      await new Promise((resolve, reject) => {
        const img = new Image();
        const localUrl = URL.createObjectURL(blob);
        img.onload = () => {
          const scale = Math.max(viewportWidth / img.naturalWidth, viewportHeight / img.naturalHeight);
          const drawWidth = Math.max(1, Math.floor(img.naturalWidth * scale));
          const drawHeight = Math.max(1, Math.floor(img.naturalHeight * scale));
          const dx = Math.floor((viewportWidth - drawWidth) / 2);
          const dy = Math.floor((viewportHeight - drawHeight) / 2);
          outputCtx.clearRect(0, 0, viewportWidth, viewportHeight);
          outputCtx.drawImage(img, dx, dy, drawWidth, drawHeight);
          URL.revokeObjectURL(localUrl);
          resolve();
        };
        img.onerror = () => {
          URL.revokeObjectURL(localUrl);
          reject(new Error('frame_decode_failed'));
        };
        img.src = localUrl;
      });

      return true;
    };

    const parseApiErrorMessage = async (err) => {
      const statusCode = err?.response?.status;
      const payload = err?.response?.data;
      if (payload instanceof Blob) {
        try {
          const text = await payload.text();
          if (text) {
            try {
              const parsed = JSON.parse(text);
              const msg = parsed?.error || parsed?.message || parsed?.msg;
              if (msg) return String(msg);
            } catch (_) {
              const compact = text.replace(/\s+/g, ' ').trim();
              if (compact.toLowerCase().includes('too many requests')) {
                return 'Frame upload is being rate-limited. Retrying automatically...';
              }
              if (compact.toLowerCase().includes('could not proxy request') || compact.toLowerCase().includes('econnreset')) {
                return 'Backend connection reset. Ensure backend server is running on port 5000 and retry.';
              }
              return compact.slice(0, 220);
            }
          }
        } catch (_) {
          // noop
        }
      } else if (payload && typeof payload === 'object') {
        const msg = payload.error || payload.message || payload.msg;
        if (msg) return String(msg);
      }

      if (statusCode === 401 || statusCode === 422) {
        return 'Session expired. Please login again.';
      }
      if (statusCode === 400) {
        return 'Invalid camera frame received by backend. Try retry and grant camera permission.';
      }
      if (statusCode === 500) {
        return 'Backend failed to process frame. Check backend logs and model dependencies.';
      }
      if (err?.message) {
        const compact = String(err.message).replace(/\s+/g, ' ').trim();
        if (compact) {
          return compact.slice(0, 240);
        }
      }
      return 'Failed to process device camera frame. Verify backend reachability and event state.';
    };

    const processNextFrame = async () => {
      if (cancelled) return;
      const videoEl = videoRef.current;
      const canvasEl = canvasRef.current;
      if (!videoEl || !canvasEl || videoEl.readyState < 2) {
        scheduleNext(120);
        return;
      }

      const sourceWidth = videoEl.videoWidth || 0;
      const sourceHeight = videoEl.videoHeight || 0;
      if (sourceWidth < 2 || sourceHeight < 2) {
        scheduleNext(120);
        return;
      }

      // Keep frame payload lighter to reduce UI lag and network churn.
      const maxWidth = isPhoneClient ? 320 : 416;
      const scale = Math.min(1, maxWidth / sourceWidth);
      const nextCanvasWidth = Math.max(2, Math.floor(sourceWidth * scale));
      const nextCanvasHeight = Math.max(2, Math.floor(sourceHeight * scale));
      if (canvasEl.width !== nextCanvasWidth) canvasEl.width = nextCanvasWidth;
      if (canvasEl.height !== nextCanvasHeight) canvasEl.height = nextCanvasHeight;
      const ctx = canvasEl.getContext('2d', { alpha: false });
      if (!ctx) {
        scheduleNext(140);
        return;
      }
      ctx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);

      const blob = await new Promise((resolve) => {
        const jpegQuality = isPhoneClient ? 0.50 : 0.58;
        if (typeof canvasEl.toBlob === 'function') {
          canvasEl.toBlob(resolve, 'image/jpeg', jpegQuality);
          return;
        }
        try {
          const dataUrl = canvasEl.toDataURL('image/jpeg', jpegQuality);
          fetch(dataUrl)
            .then((res) => res.blob())
            .then(resolve)
            .catch(() => resolve(null));
        } catch (_) {
          resolve(null);
        }
      });
      if (!blob) {
        scheduleNext(120);
        return;
      }

      const cameraId = selectedCamera?.camera_id || 'EVENT_DEFAULT';
      const url = `/camera/process-client-frame?camera_id=${encodeURIComponent(cameraId)}`;
      const requestStartedAt = performance.now();

      try {
        const response = await api.post(url, blob, {
          headers: {
            'Content-Type': 'application/octet-stream',
          },
          responseType: 'blob',
          timeout: hasRenderedFrame ? 30000 : 90000,
        });

        const contentType = String(response?.headers?.['content-type'] || '').toLowerCase();
        if (!contentType.includes('image/')) {
          let text = '';
          try {
            text = await response.data.text();
          } catch (_) {
            text = '';
          }
          const compact = String(text || '').replace(/\s+/g, ' ').trim();
          throw new Error(compact || 'Backend returned non-image response while processing camera frame.');
        }

        if (!cancelled) {
          const elapsedMs = Math.max(1, performance.now() - requestStartedAt);
          avgRttMsRef.current = (avgRttMsRef.current * 0.7) + (elapsedMs * 0.3);
          const minGap = isPhoneClient ? 12 : 6;
          const maxGap = isPhoneClient ? 45 : 28;
          retryDelayMs = Math.min(
            maxGap,
            Math.max(minGap, Math.round(avgRttMsRef.current * 0.03)),
          );

          if (liveFeedEnabled) {
            await drawProcessedBlob(response.data);
            setHasProcessedFrame(true);
          } else {
            setHasProcessedFrame(false);
          }
          const nowMs = Date.now();
          const fpsWindow = fpsWindowRef.current;
          if (!fpsWindow.startMs) {
            fpsWindow.startMs = nowMs;
            fpsWindow.frames = 1;
          } else {
            fpsWindow.frames += 1;
            const elapsedMs = nowMs - fpsWindow.startMs;
            if (elapsedMs >= 1000) {
              const fpsValue = (fpsWindow.frames * 1000) / Math.max(1, elapsedMs);
              setLiveFps((prev) => {
                if (!Number.isFinite(prev) || prev <= 0) return fpsValue;
                return (prev * 0.6) + (fpsValue * 0.4);
              });
              fpsWindow.startMs = nowMs;
              fpsWindow.frames = 0;
            }
          }
          setStreamError('');
          hasRenderedFrame = true;
          setIsFramePending(false);
          setBackendUnavailable(false);
        }
      } catch (err) {
        if (!cancelled) {
          const msg = await parseApiErrorMessage(err);
          setStreamError(msg);
          if (
            String(msg).toLowerCase().includes('backend connection reset') ||
            String(msg).toLowerCase().includes('verify backend reachability')
          ) {
            setBackendUnavailable(true);
          }
          setIsFramePending(false);
          retryDelayMs = Math.min(Math.max(retryDelayMs * 1.4, 60), 1200);
        }
      }
      scheduleNext();
    };

    const startClientCamera = async () => {
      if (!navigator?.mediaDevices?.getUserMedia) {
        setDeviceError('Device camera API is unavailable in this browser.');
        return;
      }

      try {
        setDeviceError('');
        setStreamError('');
        clearProcessedFrame();

        let stream = null;
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: { exact: cameraFacingMode },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
            audio: false,
          });
        } catch (_exactError) {
          try {
            stream = await navigator.mediaDevices.getUserMedia({
              video: {
                facingMode: { ideal: cameraFacingMode },
                width: { ideal: 1280 },
                height: { ideal: 720 },
              },
              audio: false,
            });
          } catch (_) {
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
          }
        }

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        localStreamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          try {
            await videoRef.current.play();
          } catch (_) {
            // keep capturing via stream even if explicit play fails on browser policy
          }
        }
        setIsFramePending(true);
        scheduleNext(80);
      } catch (err) {
        if (!cancelled) {
          setDeviceError('Unable to access this device camera. Allow permission and retry.');
          setIsFramePending(false);
        }
      }
    };

    startClientCamera();
    return () => {
      cancelled = true;
      if (timerId) window.clearTimeout(timerId);
      stopLocalCamera(false);
    };
  }, [cameraFacingMode, clearProcessedFrame, isClientDeviceMode, isPhoneClient, liveFeedEnabled, selectedCamera?.camera_id, stopLocalCamera]);

  useEffect(() => () => stopLocalCamera(true), [stopLocalCamera]);

  const streamSrc = selectedCamera
    ? `${String(api.defaults.baseURL).replace(/\/$/, '')}/camera/feed/${selectedCamera.camera_id}?t=${streamNonce}`
    : '';
  const backendFps = Number(runtimeInfo?.fps || 0);
  const aiFps = Number(runtimeInfo?.ai_fps || 0);
  const displayFps = isClientDeviceMode ? liveFps : backendFps;
  const displayFpsLabel = `${Math.max(0, displayFps).toFixed(1)} FPS`;
  const aiFpsLabel = `${Math.max(0, aiFps).toFixed(1)} FPS`;

  if (loading) return <div className="p-6">Loading cameras...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Live Camera Feed</h1>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <button
            type="button"
            className={liveFeedEnabled ? 'btn btn-danger' : 'btn btn-primary'}
            onClick={() => {
              setStreamError('');
              setDeviceError('');
              setLiveFeedEnabled((prev) => {
                const next = !prev;
                if (next) {
                  setStreamNonce(Date.now());
                }
                return next;
              });
            }}
          >
            {liveFeedEnabled ? 'Turn Feed Off' : 'Turn Feed On'}
          </button>
          {isClientDeviceMode && isPhoneClient && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setStreamError('');
                setDeviceError('');
                setCameraFacingMode((prev) => (prev === 'user' ? 'environment' : 'user'));
              }}
            >
              {isSelfieMode ? 'Use Rear Camera' : 'Use Selfie Camera'}
            </button>
          )}
          <select 
            className="input w-64"
            value={selectedCamera?.camera_id || ''}
            onChange={(e) => handleCameraChange(e.target.value)}
          >
            {cameras.length === 0 && <option value="">No cameras configured</option>}
            {cameras.map(cam => (
              <option key={cam.id} value={cam.camera_id}>{cam.name}</option>
            ))}
          </select>
        </div>
      </div>
      {eventInfo?.event_name && (
        <div className="text-sm text-gray-600">
          Event: <strong>{eventInfo.event_name}</strong> | Status: <strong>{eventInfo.status}</strong> | Feed: <strong>{liveFeedEnabled ? 'On' : 'Off'}</strong> | Display FPS: <strong>{displayFpsLabel}</strong> | AI FPS: <strong>{aiFpsLabel}</strong>
        </div>
      )}
      {isClientDeviceMode && eventInfo?.status === 'active' && (
        <div className="text-sm text-amber-500">
          Realtime performance mode is optimized for backend-owned cameras (Existing/RTSP).
        </div>
      )}
      {runtimeInfo?.last_error && !isClientDeviceMode && (
        <div className="text-sm text-amber-500">
          Camera runtime: {runtimeInfo.last_error}
        </div>
      )}
      {backendUnavailable && (
        <div className="text-sm text-red-600">
          Backend appears unreachable right now. Confirm backend is running at `http://127.0.0.1:5000`.
        </div>
      )}

      {selectedCamera ? (
        <div className="bg-black rounded-lg overflow-hidden h-[600px] flex items-center justify-center relative">
          {deviceError ? (
            <div className="text-center text-white p-6">{deviceError}</div>
          ) : !liveFeedEnabled ? (
            <>
              {isClientDeviceMode && (
                <>
                  <video
                    ref={videoRef}
                    autoPlay
                    muted
                    playsInline
                    disablePictureInPicture
                    disableRemotePlayback
                    controlsList="nodownload noplaybackrate noremoteplayback nofullscreen"
                    style={isSelfieMode ? { transform: 'scaleX(-1)' } : undefined}
                    className="absolute -left-[10000px] top-0 h-[1px] w-[1px] opacity-0 pointer-events-none"
                  />
                  <canvas ref={processedCanvasRef} className="hidden" aria-label="Processed Device Feed" />
                  <canvas ref={canvasRef} className="hidden" />
                </>
              )}
              <div className="text-center text-white p-6 max-w-2xl">
                Live feed is turned off. Backend processing remains active for scheduled event cameras.
              </div>
            </>
          ) : streamError ? (
            <div className="text-center text-white p-6">
              <p className="mb-3">{streamError}</p>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setStreamError('');
                  setStreamNonce(Date.now());
                }}
              >
                Retry Stream
              </button>
            </div>
          ) : isClientDeviceMode ? (
            <>
              <video
                ref={videoRef}
                autoPlay
                muted
                playsInline
                disablePictureInPicture
                disableRemotePlayback
                controlsList="nodownload noplaybackrate noremoteplayback nofullscreen"
                style={isSelfieMode ? { transform: 'scaleX(-1)' } : undefined}
                className={
                  hasProcessedFrame
                    ? 'absolute -left-[10000px] top-0 h-[1px] w-[1px] opacity-0 pointer-events-none'
                    : 'w-full h-full object-cover'
                }
              />
              <canvas
                ref={processedCanvasRef}
                className={`absolute inset-0 z-20 w-full h-full ${hasProcessedFrame ? '' : 'hidden'}`}
                aria-label="Processed Device Feed"
              />
              <canvas ref={canvasRef} className="hidden" />
            </>
          ) : (
            <img 
              key={`${selectedCamera?.camera_id || 'camera'}-${streamNonce}`}
              src={streamSrc}
              alt="Live Feed" 
              className="w-full h-full object-cover"
              style={{ imageRendering: 'auto' }}
              onError={() => setStreamError('Failed to load camera stream. Verify camera source and backend OpenCV access.')}
            />
          )}
          {isClientDeviceMode && isFramePending && !hasProcessedFrame && !streamError && !deviceError && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/60 text-white text-sm px-3 py-1 rounded">
              Initializing camera stream...
            </div>
          )}
        </div>
      ) : (
        <div className="text-center p-12 text-gray-500">No cameras available</div>
      )}
    </div>
  );
}
