import { useAuth } from "../auth/AuthContext.jsx";
import { Button } from "../components/Button.jsx";
import { Card } from "../components/Card.jsx";

/** Placeholder landing page -- real Create/Join Account + Account
 * Switcher UI lands in the next branch (milestone 2). This just proves
 * the whole login -> protected route chain works end-to-end already. */
export function OnboardingStub() {
  const { logout, userId, role, accountId } = useAuth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-50 px-4">
      <Card className="max-w-md text-center">
        <h1 className="mb-2 text-lg font-semibold text-gray-900">You're logged in 🎉</h1>
        <p className="mb-4 text-sm text-gray-500">
          Onboarding (create/join account, account switcher) lands in the next branch.
        </p>
        <p className="mb-4 text-xs text-gray-400">
          user: {userId} · account: {accountId ?? "none yet"} · role: {role ?? "n/a"}
        </p>
        <Button variant="outline" onClick={logout}>
          Log out
        </Button>
      </Card>
    </div>
  );
}