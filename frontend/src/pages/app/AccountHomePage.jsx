import { useAuth } from "../../auth/AuthContext.jsx";
import { Card } from "../../components/Card.jsx";
import { OwnerDashboardPage } from "./OwnerDashboardPage.jsx";

export function AccountHomePage() {
  const { role } = useAuth();

  if (role === "owner") return <OwnerDashboardPage />;

  return (
    <Card className="max-w-md">
      <h1 className="mb-2 text-lg font-semibold text-gray-900">Welcome back</h1>
      <p className="text-sm text-gray-500">
        Head to Content Studio to draft a post, or check the Calendar for anything scheduled.
      </p>
    </Card>
  );
}