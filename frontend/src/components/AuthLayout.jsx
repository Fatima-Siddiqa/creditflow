import { Link } from "react-router-dom";
import { Logo } from "./Logo.jsx";
import { Card } from "./Card.jsx";

export function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-50 px-4">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-6 flex justify-center">
          <Logo />
        </Link>
        <Card>
          <h1 className="mb-1 text-xl font-semibold text-gray-900">{title}</h1>
          {subtitle && <p className="mb-6 text-sm text-gray-500">{subtitle}</p>}
          {children}
        </Card>
      </div>
    </div>
  );
}