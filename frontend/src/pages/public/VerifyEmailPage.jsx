import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthLayout } from "../../components/AuthLayout.jsx";
import { api } from "../../api/client.js";

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState("pending"); // pending | success | error

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    (async () => {
      const res = await api.post("auth/verify-email", { token });
      setStatus(res.ok ? "success" : "error");
    })();
  }, [token]);

  return (
    <AuthLayout title="Email verification">
      {status === "pending" && <p className="text-sm text-gray-600">Verifying your email…</p>}
      {status === "success" && (
        <>
          <p className="mb-4 text-sm text-gray-600">Your email is verified. You can log in now.</p>
          <Link to="/login" className="text-sm font-medium text-brand-700 hover:underline">
            Go to log in
          </Link>
        </>
      )}
      {status === "error" && (
        <p className="text-sm text-red-600">This verification link is invalid or has expired.</p>
      )}
    </AuthLayout>
  );
}