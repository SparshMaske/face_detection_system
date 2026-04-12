function asDate(value) {
  if (!value) return null;
  const dt = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(dt.getTime())) return null;
  return dt;
}

export function formatDateTime12h(value, fallback = 'N/A') {
  const dt = asDate(value);
  if (!dt) return fallback;
  return dt.toLocaleString(undefined, {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
}

export function formatDateOnly(value, fallback = 'N/A') {
  const dt = asDate(value);
  if (!dt) return fallback;
  return dt.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  });
}

export function formatTime12h(value, fallback = 'N/A') {
  const dt = asDate(value);
  if (!dt) return fallback;
  return dt.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

export function toDateTimeLocalInput(value) {
  const dt = asDate(value);
  if (!dt) return '';
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const dd = String(dt.getDate()).padStart(2, '0');
  const hh = String(dt.getHours()).padStart(2, '0');
  const mi = String(dt.getMinutes()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

export function localDateInputValue(value = new Date()) {
  const dt = asDate(value);
  if (!dt) return '';
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const dd = String(dt.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export function localTimeInputValue(value = new Date()) {
  const dt = asDate(value);
  if (!dt) return '';
  const hh = String(dt.getHours()).padStart(2, '0');
  const mi = String(dt.getMinutes()).padStart(2, '0');
  return `${hh}:${mi}`;
}
