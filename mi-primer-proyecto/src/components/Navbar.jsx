import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Map,
  FolderOpen,
  Bell,
  Settings,
  Shield,
} from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/mapa", label: "Mapa", icon: Map },
  { to: "/documentos", label: "Documentos", icon: FolderOpen },
];

export default function Navbar() {
  return (
    <aside className="navbar">
      {/* Logo */}
      <div className="navbar-logo">
        <div className="navbar-logo-icon">
          <Shield size={20} />
        </div>
        <div className="navbar-logo-text">
          <span className="navbar-logo-title">GestiónDoc</span>
          <span className="navbar-logo-sub">Trámites y Cumplimiento</span>
        </div>
      </div>

      {/* Links */}
      <nav className="navbar-nav">
        <span className="navbar-section-label">Principal</span>
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            className={({ isActive }) =>
              `navbar-link ${isActive ? "active" : ""}`
            }
          >
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer links */}
      <div className="navbar-footer">
        <button className="navbar-link">
          <Bell size={18} />
          <span>Alertas</span>
          <span className="navbar-badge">4</span>
        </button>
        <button className="navbar-link">
          <Settings size={18} />
          <span>Configuración</span>
        </button>
      </div>
    </aside>
  );
}
