import { useEffect, useState } from 'react';
import { getStaff, deleteStaff, createStaff } from '../services/staffService';
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
    const formData = new FormData();
    Object.keys(newStaff).forEach(key => formData.append(key, newStaff[key]));
    images.forEach((img) => formData.append('images', img));
    
    try {
      await createStaff(formData);
      setIsModalOpen(false);
      fetchStaff();
      setNewStaff({ staff_id: '', name: '', department: '', position: '', email: '', phone: '' });
    } catch (err) {
      setError(err?.response?.data?.error || 'Failed to create staff member');
    }
  };

  if (loading) return <div className="p-6">Loading staff...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Staff Management</h1>
        <button onClick={() => setIsModalOpen(true)} className="btn btn-primary">Add Staff</button>
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
          <input className="input" placeholder="Staff ID (e.g. EMP001)" required
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
            <label className="block text-sm mb-1">Upload Photos</label>
            <input type="file" multiple accept="image/*" 
              onChange={e => setImages(Array.from(e.target.files || []))} className="input" />
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
