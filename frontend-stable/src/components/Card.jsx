export default function Card({ title, children, className = "" }) {
  return (
    <div className={`card p-6 ${className}`}>
      {title && <h3 className="text-lg font-semibold mb-4 text-gray-800">{title}</h3>}
      {children}
    </div>
  );
}
