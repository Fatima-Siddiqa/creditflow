export function Card({ children, className = "" }) {
  return <div className={`rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-100 ${className}`}>{children}</div>;
}