import { useEffect, useState } from 'react';
import { getStaff, deleteStaff, createStaff } from '../services/staffService';
import api from '../services/api';
import Modal from '../components/Modal';
import Card from '../components/Card';

export default function StaffManagement() {
  const [staff, setStaff] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newStaff, setNewStaff] = useState({
    staff_id: '', name: '', department: '', position: '', email: '', phone: ''
  });
  const [images, setImages] = useState([]);
  const [cameraOptions, setCameraOptions] = useState([]);
  const [selectedCaptureCameraId, setSelectedCaptureCameraId] = useState('');
  const [captureLoading, setCaptureLoading] = useState(false);
  const [captureError, setCaptureError] = useState('');

  const fetchStaff = async () => {
    try {
      setError('');
      const res = await getStaff();
      setStaff(res.data || []);
    } catch (err) {
      setError('Failed to load staff data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStaff(); }, []);

  const openAddStaffModal = async () => {
    setError('');
    setCaptureError('');
    setIsModalOpen(true);
    try {
      const res = await api.get('/camera/');
      const list = Array.isArray(res?.data) ? res.data : [];
      const usable = list.filter((cam) => String(cam?.camera_type || '').toLowerCase() !== 'browser');
      setCameraOptions(usable);
      if (usable.length > 0) {
        setSelectedCaptureCameraId((prev) => prev || usable[0].camera_id);
      } else {
        setSelectedCaptureCameraId('');
      }
    } catch (_) {
      setCameraOptions([]);
      setSelectedCaptureCameraId('');
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this staff member?')) {
      try {
        await deleteStaff(id);
        fetchStaff();
      } catch (err) {
        setError('Failed to delete staff member');
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setCaptureError('');
    if (!(newStaff.name || '').trim()) {
      setError('Full Name is required');
      return;
    }
    if (!images.length) {
      setError('At least one image is required (upload or capture from camera).');
      return;
    }
    const formData = new FormData();
    Object.entries(newStaff).forEach(([key, value]) => {
      if ((value || '').toString().trim()) {
        formData.append(key, value);
      }
    });
    images.forEach((img) => formData.append('images', img));
    
    try {
      await createStaff(formData);
      setIsModalOpen(false);
      fetchStaff();
      setNewStaff({ staff_id: '', name: '', department: '', position: '', email: '', phone: '' });
      setImages([]);
      setCameraOptions([]);
      setSelectedCaptureCameraId('');
    } catch (err) {
      setError(err?.response?.data?.error || 'Failed to create staff member');
    }
  };

  const handleCaptureFromCamera = async () => {
    setCaptureError('');
    setError('');
    if (!selectedCaptureCameraId) {
      setCaptureError('Select a configured backend camera first.');
      return;
    }
    setCaptureLoading(true);
    try {
      const res = await api.get('/staff/capture-photo', {
        params: { camera_id: selectedCaptureCameraId },
        responseType: 'blob',
      });
      const mime = String(res?.headers?.['content-type'] || '').toLowerCase();
      if (!mime.includes('image/')) {
        const text = await res.data.text();
        throw new Error(text || 'Failed to capture image from camera');
      }
      const file = new File(
        [res.data],
        `staff_capture_${Date.now()}.jpg`,
        { type: mime || 'image/jpeg' }
      );
      setImages((prev) => [...prev, file]);
    } catch (err) {
      let msg = err?.message || 'Failed to capture image from selected camera';
      const payload = err?.response?.data;
      if (payload instanceof Blob) {
        try {
          const text = await payload.text();
          if (text) {
            try {
              const parsed = JSON.parse(text);
              msg = parsed?.error || parsed?.message || msg;
            } catch (_) {
              msg = text;
            }
          }
        } catch (_) {
          // ignore
        }
      } else if (payload?.error) {
        msg = payload.error;
      }
      setCaptureError(msg);
    } finally {
      setCaptureLoading(false);
    }
  };

  if (loading) return <div className="p-6">Loading staff...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Staff Management</h1>
        <button onClick={openAddStaffModal} className="btn btn-primary">Add Staff</button>
      </div>

      <Card>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Dept</th>
              <th>Email</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {staff.map(s => (
              <tr key={s.id}>
                <td>{s.staff_id}</td>
                <td>{s.name}</td>
                <td>{s.department}</td>
                <td>{s.email}</td>
                <td>
                  <button onClick={() => handleDelete(s.id)} className="btn btn-danger text-xs">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title="Add New Staff">
        <form onSubmit={handleSubmit} className="space-y-4">
          <input className="input" placeholder="Staff ID (optional, auto-generated if empty)"
            value={newStaff.staff_id} onChange={e => setNewStaff({...newStaff, staff_id: e.target.value})} />
          <input className="input" placeholder="Full Name" required
            value={newStaff.name} onChange={e => setNewStaff({...newStaff, name: e.target.value})} />
          <div className="flex gap-4">
            <input className="input" placeholder="Department"
              value={newStaff.department} onChange={e => setNewStaff({...newStaff, department: e.target.value})} />
            <input className="input" placeholder="Position"
              value={newStaff.position} onChange={e => setNewStaff({...newStaff, position: e.target.value})} />
          </div>
          <input className="input" type="email" placeholder="Email"
            value={newStaff.email} onChange={e => setNewStaff({...newStaff, email: e.target.value})} />
          <input className="input" placeholder="Phone"
            value={newStaff.phone} onChange={e => setNewStaff({...newStaff, phone: e.target.value})} />
          
          <div>
            <label className="block text-sm mb-1">Upload Photos (required)</label>
            <input type="file" multiple accept="image/*" 
              onChange={e => setImages(Array.from(e.target.files || []))} className="input" />
          </div>
          <div className="space-y-2">
            <label className="block text-sm mb-1">Capture From Configured Camera (Raspberry/RTSP/Webcam)</label>
            <div className="flex gap-2 items-center">
              <select
                className="input"
                value={selectedCaptureCameraId}
                onChange={(e) => setSelectedCaptureCameraId(e.target.value)}
              >
                <option value="">Select camera</option>
                {cameraOptions.map((cam) => (
                  <option key={cam.camera_id} value={cam.camera_id}>{cam.name}</option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={captureLoading || !selectedCaptureCameraId}
                onClick={handleCaptureFromCamera}
              >
                {captureLoading ? 'Capturing...' : 'Capture Photo'}
              </button>
            </div>
            {captureError && <div className="text-sm text-red-500">{captureError}</div>}
            <div className="text-xs text-gray-500">Selected images: {images.length}</div>
          </div>

          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setIsModalOpen(false)} className="btn btn-secondary">Cancel</button>
            <button type="submit" className="btn btn-primary">Save</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
