import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthLayout } from "../../components/AuthLayout.jsx";
import { TextInput } from "../../components/TextInput.jsx";
import { Button } from "../../components/Button.jsx";
import { useAuth } from "../../auth/AuthContext.jsx";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      const redirectTo = location.state?.from?.pathname || "/app";
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Log in to CreditFlow">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <TextInput label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <TextInput
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex items-center justify-between text-sm">
          <Link to="/forgot-password" className="text-brand-700 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? "Logging in…" : "Log in"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-500">
        Don't have an account?{" "}
        <Link to="/signup" className="font-medium text-brand-700 hover:underline">
          Sign up
        </Link>
      </p>
    </AuthLayout>
  );
}