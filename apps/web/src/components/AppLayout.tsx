import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export function AppLayout() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "font-medium text-accent" : "text-muted hover:text-fg";

  return (
    <div className="min-h-screen bg-page">
      <header className="border-b border-border bg-surface px-6 py-3">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <NavLink to="/" className="text-lg font-semibold text-fg">Lewis</NavLink>
          <nav className="flex items-center gap-5 text-sm">
            <NavLink to="/" end className={linkClass}>Chat</NavLink>
            <NavLink to="/saved" className={linkClass}>Saved</NavLink>
            <NavLink to="/onboarding" className={linkClass}>Profile</NavLink>
            <button type="button" onClick={handleLogout} className="text-muted hover:text-fg">
              Logout
            </button>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
