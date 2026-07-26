import { useAuth } from "../../auth/AuthContext.jsx";
import { Card } from "../../components/Card.jsx";

export function AccountHomePage() {
  const { userId, accountId, role } = useAuth();
  return (
    <Card className="max-w-md">
      <h1 className="mb-2 text-lg font-semibold text-gray-900">Account home</h1>
      <p className="text-sm text-gray-500">user: {userId} · account: {accountId} · role: {role}</p>
    </Card>
  );
}