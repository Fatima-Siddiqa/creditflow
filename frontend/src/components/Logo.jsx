import logo from "../assets/logo.png";

export function Logo({ size = 40, showWordmark = true }) {
  return (
    <div className="flex items-center gap-2">
      <img src={logo} alt="CreditFlow" style={{ height: size, width: size }} className="rounded-md" />
      {showWordmark && <span className="text-lg font-semibold text-brand-800">CreditFlow</span>}
    </div>
  );
}