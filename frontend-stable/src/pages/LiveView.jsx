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
  const [processedFrameUrl, setProcessedFrameUrl] = useState('');
  const [deviceError, setDeviceError] = useState('');
  const [isFramePending, setIsFramePending] = useState(false);
  const [cameraFacingMode, setCameraFacingMode] = useState('environment');
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const localStreamRef = useRef(null);
  const frameUrlRef = useRef('');

  const clearProcessedFrame = useCallback(() => {
    if (frameUrlRef.current) {
      URL.revokeObjectURL(frameUrlRef.current);
      frameUrlRef.current = '';
    }
    setProcessedFrameUrl('');
  }, []);

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
      }
    } catch (_) {
      setError('Failed to load camera list. Check backend connection and login token.');
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
    }, 5000);
    return () => window.clearInterval(id);
  }, [fetchCamerasAndEvent]);

  const handleCameraChange = (cameraId) => {
    const camera = cameras.find((c) => c.camera_id === cameraId) || null;
    setSelectedCamera(camera);
    setStreamError('');
    setDeviceError('');
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
    if (!isClientDeviceMode) {
      stopLocalCamera(true);
      return undefined;
    }

    let cancelled = false;
    let timerId = null;
    let hasRenderedFrame = false;

    const scheduleNext = (delayMs = 260) => {
      if (cancelled) return;
      timerId = window.setTimeout(processNextFrame, delayMs);
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
              return text.slice(0, 220);
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
      return 'Failed to process device camera frame. Verify backend reachability and event state.';
    };

    const processNextFrame = async () => {
      if (cancelled) return;
      const videoEl = videoRef.current;
      const canvasEl = canvasRef.current;
      if (!videoEl || !canvasEl || videoEl.readyState < 2) {
        scheduleNext(300);
        return;
      }

      const sourceWidth = videoEl.videoWidth || 0;
      const sourceHeight = videoEl.videoHeight || 0;
      if (sourceWidth < 2 || sourceHeight < 2) {
        scheduleNext(300);
        return;
      }

      const maxWidth = 960;
      const scale = Math.min(1, maxWidth / sourceWidth);
      canvasEl.width = Math.max(2, Math.floor(sourceWidth * scale));
      canvasEl.height = Math.max(2, Math.floor(sourceHeight * scale));
      const ctx = canvasEl.getContext('2d', { alpha: false });
      if (!ctx) {
        scheduleNext(350);
        return;
      }
      ctx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);

      const blob = await new Promise((resolve) => {
        if (typeof canvasEl.toBlob === 'function') {
          canvasEl.toBlob(resolve, 'image/jpeg', 0.82);
          return;
        }
        try {
          const dataUrl = canvasEl.toDataURL('image/jpeg', 0.82);
          fetch(dataUrl)
            .then((res) => res.blob())
            .then(resolve)
            .catch(() => resolve(null));
        } catch (_) {
          resolve(null);
        }
      });
      if (!blob) {
        scheduleNext(300);
        return;
      }

      const cameraId = selectedCamera?.camera_id || 'EVENT_DEFAULT';
      const url = `/camera/process-client-frame?camera_id=${encodeURIComponent(cameraId)}`;

      try {
        setIsFramePending(true);
        const response = await api.post(url, blob, {
          headers: {
            'Content-Type': 'application/octet-stream',
          },
          responseType: 'blob',
          timeout: hasRenderedFrame ? 30000 : 90000,
        });

        if (!cancelled) {
          const nextUrl = URL.createObjectURL(response.data);
          if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current);
          frameUrlRef.current = nextUrl;
          setProcessedFrameUrl(nextUrl);
          setStreamError('');
          hasRenderedFrame = true;
        }
      } catch (err) {
        if (!cancelled) {
          const msg = await parseApiErrorMessage(err);
          setStreamError(msg);
        }
      } finally {
        if (!cancelled) {
          setIsFramePending(false);
        }
        scheduleNext(260);
      }
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
        scheduleNext(120);
      } catch (err) {
        if (!cancelled) {
          setDeviceError('Unable to access this device camera. Allow permission and retry.');
        }
      }
    };

    startClientCamera();
    return () => {
      cancelled = true;
      if (timerId) window.clearTimeout(timerId);
      stopLocalCamera(false);
    };
  }, [cameraFacingMode, clearProcessedFrame, isClientDeviceMode, selectedCamera?.camera_id, stopLocalCamera]);

  useEffect(() => () => stopLocalCamera(true), [stopLocalCamera]);

  const streamSrc = selectedCamera
    ? `${String(api.defaults.baseURL).replace(/\/$/, '')}/camera/feed/${selectedCamera.camera_id}?t=${streamNonce}`
    : '';

  if (loading) return <div className="p-6">Loading cameras...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Live Camera Feed</h1>
        <div className="flex items-center gap-2 flex-wrap justify-end">
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
          Event: <strong>{eventInfo.event_name}</strong> | Status: <strong>{eventInfo.status}</strong>
        </div>
      )}

      {selectedCamera ? (
        <div className="bg-black rounded-lg overflow-hidden h-[600px] flex items-center justify-center relative">
          {deviceError ? (
            <div className="text-center text-white p-6">{deviceError}</div>
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
                style={isSelfieMode ? { transform: 'scaleX(-1)' } : undefined}
                className={`w-full h-full object-contain ${processedFrameUrl ? 'opacity-0 absolute inset-0 pointer-events-none' : ''}`}
              />
              {processedFrameUrl && (
                <img
                  src={processedFrameUrl}
                  alt="Processed Device Feed"
                  className="w-full h-full object-contain"
                />
              )}
              <canvas ref={canvasRef} className="hidden" />
            </>
          ) : (
            <img 
              src={streamSrc}
              alt="Live Feed" 
              className="w-full h-full object-contain"
              onError={() => setStreamError('Failed to load camera stream. Verify camera source and backend OpenCV access.')}
            />
          )}
          <div className="absolute top-4 left-4 bg-black/50 text-white px-2 py-1 rounded text-sm">
            {isClientDeviceMode
              ? `${selectedCamera.name} (This Device${isPhoneClient ? ` • ${isSelfieMode ? 'Selfie' : 'Rear'}` : ''})`
              : selectedCamera.name}
          </div>
          {isClientDeviceMode && isFramePending && !processedFrameUrl && !streamError && !deviceError && (
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
