import { Routes, Route } from "react-router-dom";
import { HomePage } from "./pages/public/HomePage.jsx";
import { SignupPage } from "./pages/public/SignupPage.jsx";
import { LoginPage } from "./pages/public/LoginPage.jsx";
import { ForgotPasswordPage } from "./pages/public/ForgotPasswordPage.jsx";
import { VerifyEmailPage } from "./pages/public/VerifyEmailPage.jsx";
import { OnboardingStub } from "./pages/OnboardingStub.jsx";
import { ProtectedRoute } from "./auth/ProtectedRoute.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      {/* Onboarding proper (create/join account, account switcher) lands
          in the next branch -- this stub just proves the login -> landing
          redirect and route guard work end-to-end already. */}
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <OnboardingStub />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<HomePage />} />
    </Routes>
  );
}