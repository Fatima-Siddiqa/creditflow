import { useState } from "react";
import { Link } from "react-router-dom";
import { AuthLayout } from "../../components/AuthLayout.jsx";
import { TextInput } from "../../components/TextInput.jsx";
import { Button } from "../../components/Button.jsx";
import { api } from "../../api/client.js";

export function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  function validate() {
    const next = {};
    if (!/^\S+@\S+\.\S+$/.test(email)) next.email = "Enter a valid email address.";
    if (password.length < 8) next.password = "Password must be at least 8 characters.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    try {
      const res = await api.post("auth/signup", { email, password });
      const data = await res.json();
      if (!res.ok) {
        setErrors({ form: data?.error?.message || "Signup failed." });
        return;
      }
      setDone(true);
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthLayout title="Check your email" subtitle="We've sent a verification link to activate your account.">
        <Link to="/login" className="text-sm text-brand-700 hover:underline">
          Back to log in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Create your account" subtitle="Start with a free plan, no card required.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <TextInput
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          required
        />
        <TextInput
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          required
        />
        {errors.form && <p className="text-sm text-red-600">{errors.form}</p>}
        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? "Creating account…" : "Sign up"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-500">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}