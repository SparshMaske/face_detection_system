function asDate(value) {
  if (!value) return null;
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return null;
    return value;
  }

  let dt = new Date(value);
  if (Number.isNaN(dt.getTime()) && typeof value === 'string') {
    const text = value.trim();
    const dateTimeMatch = text.match(
      /^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:[,\s]+(\d{1,2}):(\d{2})(?:\s*(AM|PM))?)?$/i
    );
    if (dateTimeMatch) {
      const [, d, m, y, hh = '00', mm = '00', meridiem = ''] = dateTimeMatch;
      let hour = Number.parseInt(hh, 10);
      const minute = Number.parseInt(mm, 10);
      const mer = String(meridiem || '').toUpperCase();
      if (!Number.isNaN(hour) && !Number.isNaN(minute)) {
        if (mer) {
          if (hour === 12) hour = 0;
          if (mer === 'PM') hour += 12;
        }
        dt = new Date(
          Number.parseInt(y, 10),
          Number.parseInt(m, 10) - 1,
          Number.parseInt(d, 10),
          hour,
          minute,
          0,
          0
        );
      }
    }
  }
  if (Number.isNaN(dt.getTime())) return null;
  return dt;
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function formatDatePartsDDMMYYYY(dt) {
  return `${pad2(dt.getDate())}/${pad2(dt.getMonth() + 1)}/${dt.getFullYear()}`;
}

export function formatDateTime12h(value, fallback = 'N/A') {
  const dt = asDate(value);
  if (!dt) return fallback;
  return `${formatDatePartsDDMMYYYY(dt)}, ${formatTime12h(dt, fallback)}`;
}

export function formatDateOnly(value, fallback = 'N/A') {
  const dt = asDate(value);
  if (!dt) return fallback;
  return formatDatePartsDDMMYYYY(dt);
}

export function formatTime12h(value, fallback = 'N/A') {
  const dt = asDate(value);
  if (!dt) return fallback;
  const hour24 = dt.getHours();
  const hour12 = hour24 % 12 || 12;
  const minute = pad2(dt.getMinutes());
  const meridiem = hour24 >= 12 ? 'PM' : 'AM';
  return `${hour12}:${minute} ${meridiem}`;
}

export function toDateTimeLocalInput(value) {
  const dt = asDate(value);
  if (!dt) return '';
  const yyyy = dt.getFullYear();
  const mm = pad2(dt.getMonth() + 1);
  const dd = pad2(dt.getDate());
  const hh = pad2(dt.getHours());
  const mi = pad2(dt.getMinutes());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

export function localDateInputValue(value = new Date()) {
  const dt = asDate(value);
  if (!dt) return '';
  const yyyy = dt.getFullYear();
  const mm = pad2(dt.getMonth() + 1);
  const dd = pad2(dt.getDate());
  return `${yyyy}-${mm}-${dd}`;
}

export function localTimeInputValue(value = new Date()) {
  const dt = asDate(value);
  if (!dt) return '';
  const hh = pad2(dt.getHours());
  const mi = pad2(dt.getMinutes());
  return `${hh}:${mi}`;
}
