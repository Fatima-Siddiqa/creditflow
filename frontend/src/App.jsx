import { Routes, Route, Navigate } from "react-router-dom";
import { HomePage } from "./pages/public/HomePage.jsx";
import { SignupPage } from "./pages/public/SignupPage.jsx";
import { LoginPage } from "./pages/public/LoginPage.jsx";
import { ForgotPasswordPage } from "./pages/public/ForgotPasswordPage.jsx";
import { VerifyEmailPage } from "./pages/public/VerifyEmailPage.jsx";
import { OnboardingPage } from "./pages/OnboardingPage.jsx";
import { AppLayout } from "./components/layout/AppLayout.jsx";
import { AccountHomePage } from "./pages/app/AccountHomePage.jsx";
import { TeamManagementPage } from "./pages/app/TeamManagementPage.jsx";
import { BillingPage } from "./pages/app/BillingPage.jsx";
import { CreditsMarketplacePage } from "./pages/app/CreditsMarketplacePage.jsx";
import { ContentStudioPage } from "./pages/app/ContentStudioPage.jsx";
import { CalendarPage } from "./pages/app/CalendarPage.jsx";
import { LinkedInConnectionsPage } from "./pages/app/LinkedInConnectionsPage.jsx";
import { ProtectedRoute } from "./auth/ProtectedRoute.jsx";
import { AdminConsolePage } from "./pages/app/AdminConsolePage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />

      <Route path="/app/onboarding" element={<ProtectedRoute><OnboardingPage /></ProtectedRoute>} />

      <Route path="/app" element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to="home" replace />} />
        <Route path="home" element={<AccountHomePage />} />
        <Route path="team" element={<ProtectedRoute allowedRoles={["owner"]}><TeamManagementPage /></ProtectedRoute>} />
        <Route path="billing" element={<ProtectedRoute allowedRoles={["owner"]}><BillingPage /></ProtectedRoute>} />
        <Route path="credits" element={<ProtectedRoute allowedRoles={["owner"]}><CreditsMarketplacePage /></ProtectedRoute>} />
        <Route path="studio" element={<ContentStudioPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="linkedin" element={<LinkedInConnectionsPage />} />
        <Route path="admin" element={<ProtectedRoute allowedRoles={["superadmin"]}><AdminConsolePage /></ProtectedRoute>} />
      </Route>

      <Route path="*" element={<HomePage />} />
    </Routes>
  );
}