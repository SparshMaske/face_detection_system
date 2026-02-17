import { useEffect, useState } from 'react';
import { getSettings, updateSettings } from '../services/settingsService';
import Card from '../components/Card';

const FACE_VALIDATION_SLIDERS = [
  {
    key: 'similarity_threshold',
    legacyKey: 'face_threshold',
    label: 'Similarity Threshold',
    min: 0.1,
    max: 1.0,
    step: 0.01,
    defaultValue: 0.5,
    hint: 'Higher values are stricter when matching a face against existing identities.',
  },
  {
    key: 'staff_similarity_threshold',
    label: 'Staff Match Threshold',
    min: 0.5,
    max: 1.0,
    step: 0.01,
    defaultValue: 0.65,
    hint: 'Staff is recognized when similarity is above this threshold.',
  },
  {
    key: 'blur_threshold',
    label: 'Blur Threshold',
    min: 10,
    max: 200,
    step: 1,
    defaultValue: 50,
    hint: 'Higher values reject more blurry faces.',
  },
  {
    key: 'tilt_threshold',
    label: 'Tilt Threshold',
    min: 0.1,
    max: 1.0,
    step: 0.01,
    defaultValue: 0.25,
    hint: 'Lower values are stricter for tilted faces.',
  },
  {
    key: 'min_face_area',
    label: 'Minimum Face Area (px)',
    min: 5000,
    max: 50000,
    step: 1000,
    defaultValue: 11000,
    hint: 'Faces smaller than this area are ignored.',
  },
];

export default function Settings() {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        setError('');
        const res = await getSettings();
        const rows = Array.isArray(res.data) ? res.data : [];
        const normalized = {};
        rows.forEach((item) => {
          normalized[item.key] = item.value;
        });
        setSettings(normalized);
      } catch (err) {
        setError('Failed to load system settings');
      } finally {
        setLoading(false);
      }
    };
    fetchSettings();
  }, []);

  const handleChange = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const getNumericValue = (slider) => {
    const raw = settings[slider.key] ?? (slider.legacyKey ? settings[slider.legacyKey] : undefined);
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : slider.defaultValue;
  };

  const handleSliderChange = (slider, value) => {
    const nextValue = Number(value);
    setSettings((prev) => ({
      ...prev,
      [slider.key]: nextValue,
      ...(slider.legacyKey ? { [slider.legacyKey]: nextValue } : {}),
    }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError('');
      await updateSettings(settings);
      alert('Settings updated successfully');
    } catch (err) {
      setError('Failed to update settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">System Settings</h1>
      <Card>
        <div className="space-y-4">
          {FACE_VALIDATION_SLIDERS.map((slider) => {
            const value = getNumericValue(slider);
            return (
              <div key={slider.key}>
                <label className="block text-sm font-medium mb-1">
                  {slider.label}: <strong>{value}</strong>
                </label>
                <input
                  type="range"
                  min={slider.min}
                  max={slider.max}
                  step={slider.step}
                  className="input"
                  value={value}
                  onChange={(e) => handleSliderChange(slider, e.target.value)}
                />
                <p className="text-xs text-gray-500 mt-1">{slider.hint}</p>
              </div>
            );
          })}

          <div>
            <label className="block text-sm font-medium mb-1">Data Retention (days)</label>
            <input
              type="number"
              className="input"
              value={settings.data_retention_days || 90}
              onChange={(e) => handleChange('data_retention_days', Number(e.target.value))}
            />
          </div>

          <button onClick={handleSave} className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </Card>
    </div>
  );
}
