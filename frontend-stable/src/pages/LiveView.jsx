import { useState, useEffect } from 'react';
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

  useEffect(() => {
    const fetchCameras = async () => {
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
        setEventInfo(eventRes.status === 'fulfilled' ? (eventRes.value?.data || null) : null);
        if (list.length > 0) {
          const preferredCameraId = eventRes.status === 'fulfilled'
            ? eventRes.value?.data?.selected_camera_id
            : null;
          const preferred = list.find((cam) => cam.camera_id === preferredCameraId);
          setSelectedCamera(preferred || list[0]);
          setStreamError('');
          setStreamNonce(Date.now());
        }
        if (cameraRes.status === 'rejected') {
          setError('Failed to load camera list. Check backend connection and login token.');
        }
      } catch (err) {
        setError('Failed to load camera list. Check backend connection and login token.');
      } finally {
        setLoading(false);
      }
    };
    fetchCameras();
  }, []);

  const handleCameraChange = (cameraId) => {
    const camera = cameras.find((c) => c.camera_id === cameraId) || null;
    setSelectedCamera(camera);
    setStreamError('');
    setStreamNonce(Date.now());
  };

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
          {streamError ? (
            <div className="text-center text-white p-6">
              <p className="mb-3">{streamError}</p>
              <button className="btn btn-secondary" onClick={() => setStreamNonce(Date.now())}>
                Retry Stream
              </button>
            </div>
          ) : (
            <img 
              src={streamSrc}
              alt="Live Feed" 
              className="w-full h-full object-contain"
              onError={() => setStreamError('Failed to load camera stream. Verify camera source and backend OpenCV access.')}
            />
          )}
          <div className="absolute top-4 left-4 bg-black/50 text-white px-2 py-1 rounded text-sm">
            {selectedCamera.name}
          </div>
        </div>
      ) : (
        <div className="text-center p-12 text-gray-500">No cameras available</div>
      )}
    </div>
  );
}
