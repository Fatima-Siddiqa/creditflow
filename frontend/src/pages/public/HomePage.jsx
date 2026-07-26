import { Link } from "react-router-dom";
import { Logo } from "../../components/Logo.jsx";
import { Button } from "../../components/Button.jsx";
import { Card } from "../../components/Card.jsx";

const FEATURES = [
  { title: "AI Content Generation", desc: "Draft social posts with streaming AI output, then refine and schedule." },
  { title: "Credits Marketplace", desc: "Buy, sell, and transfer credits between accounts on your own terms." },
  { title: "LinkedIn Publishing", desc: "Schedule one-off or recurring posts, published straight to LinkedIn." },
];

const PLANS = [
  { name: "Free", price: "$0", blurb: "Try the platform with a starter credit allowance." },
  { name: "Pro", price: "$29/mo", blurb: "For individuals publishing regularly." },
  { name: "Team", price: "$99/mo", blurb: "Multiple seats, shared credits, team roles." },
];

export function HomePage() {
  return (
    <div className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Logo />
        <nav className="flex items-center gap-3">
          <Link to="/login" className="text-sm font-medium text-gray-600 hover:text-brand-700">
            Log in
          </Link>
          <Link to="/signup">
            <Button>Sign up</Button>
          </Link>
        </nav>
      </header>

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight text-brand-900 sm:text-5xl">
          AI-assisted content, credit by credit.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-gray-600">
          CreditFlow lets your team generate, schedule, and publish social content — powered by a
          credit system you control.
        </p>
        <div className="mt-8">
          <Link to="/signup">
            <Button variant="accent" className="px-6 py-3 text-base">
              Get started free
            </Button>
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="grid gap-6 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title}>
              <h3 className="mb-2 font-semibold text-brand-800">{f.title}</h3>
              <p className="text-sm text-gray-600">{f.desc}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="bg-brand-50 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="mb-8 text-center text-2xl font-bold text-brand-900">Pricing</h2>
          <div className="grid gap-6 sm:grid-cols-3">
            {PLANS.map((p) => (
              <Card key={p.name} className="text-center">
                <h3 className="font-semibold text-brand-800">{p.name}</h3>
                <p className="my-2 text-2xl font-bold text-gray-900">{p.price}</p>
                <p className="text-sm text-gray-600">{p.blurb}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}