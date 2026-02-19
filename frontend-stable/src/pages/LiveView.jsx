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

  useEffect(() => {
    if (!isClientDeviceMode) {
      stopLocalCamera(true);
      return undefined;
    }

    let cancelled = false;
    let timerId = null;

    const scheduleNext = (delayMs = 260) => {
      if (cancelled) return;
      timerId = window.setTimeout(processNextFrame, delayMs);
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
        canvasEl.toBlob(resolve, 'image/jpeg', 0.82);
      });
      if (!blob) {
        scheduleNext(300);
        return;
      }

      const form = new FormData();
      form.append('frame', blob, 'frame.jpg');
      if (selectedCamera?.camera_id) {
        form.append('camera_id', selectedCamera.camera_id);
      }

      try {
        const response = await api.post('/camera/process-client-frame', form, {
          responseType: 'blob',
          timeout: 20000,
        });

        if (!cancelled) {
          const nextUrl = URL.createObjectURL(response.data);
          if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current);
          frameUrlRef.current = nextUrl;
          setProcessedFrameUrl(nextUrl);
          setStreamError('');
        }
      } catch (err) {
        if (!cancelled) {
          setStreamError(
            err?.response?.data?.error ||
              'Failed to process device camera frame. Verify backend reachability and event state.'
          );
        }
      } finally {
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
              facingMode: { ideal: 'environment' },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
            audio: false,
          });
        } catch (_) {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
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
  }, [clearProcessedFrame, isClientDeviceMode, selectedCamera?.camera_id, stopLocalCamera]);

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
            {isClientDeviceMode ? `${selectedCamera.name} (This Device)` : selectedCamera.name}
          </div>
        </div>
      ) : (
        <div className="text-center p-12 text-gray-500">No cameras available</div>
      )}
    </div>
  );
}
