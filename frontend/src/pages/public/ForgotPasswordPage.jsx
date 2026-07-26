import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../../components/AuthLayout.jsx";
import { TextInput } from "../../components/TextInput.jsx";
import { Button } from "../../components/Button.jsx";
import { api } from "../../api/client.js";

export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState("request"); // "request" -> "reset"
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function requestCode(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      // auth-service always returns the same message whether or not the
      // email exists (info-leak prevention) -- so we just move to step 2
      // regardless, exactly matching that intentional non-disclosure.
      await api.post("auth/forgot-password", { email });
      setStep("reset");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitReset(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      // auth-service's ResetPasswordRequest takes the OTP itself as `token`
      // -- there's no separate "verify code" call, code + new password go
      // together in one request.
      const res = await api.post("auth/reset-password", { token: code, new_password: newPassword });
      const data = await res.json();
      if (!res.ok) {
        setError(data?.error?.message || "Could not reset password.");
        return;
      }
      navigate("/login", { replace: true });
    } finally {
      setSubmitting(false);
    }
  }

  if (step === "request") {
    return (
      <AuthLayout title="Forgot password" subtitle="Enter your email and we'll send you a reset code.">
        <form onSubmit={requestCode} className="space-y-4" noValidate>
          <TextInput label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Sending…" : "Send reset code"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm">
          <Link to="/login" className="text-brand-700 hover:underline">
            Back to log in
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Enter your reset code" subtitle={`We sent a code to ${email} if it's registered.`}>
      <form onSubmit={submitReset} className="space-y-4" noValidate>
        <TextInput label="6-digit code" value={code} onChange={(e) => setCode(e.target.value)} required />
        <TextInput
          label="New password"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? "Resetting…" : "Reset password"}
        </Button>
      </form>
    </AuthLayout>
  );
}