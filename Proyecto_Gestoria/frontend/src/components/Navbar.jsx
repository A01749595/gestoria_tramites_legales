import { NavLink } from "react-router-dom";
import { LayoutDashboard, Map, FolderOpen, Bell, Shield, Bot, Activity } from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/mapa", label: "Mapa", icon: Map },
  { to: "/documentos", label: "Documentos", icon: FolderOpen },
  { to: "/monitoreo", label: "Agentes", icon: Activity },
  { to: "/asistente", label: "Asistente Verti", icon: Bot },
];

export default function Navbar() {
  return (
    <aside className="navbar">
      <div className="navbar-logo">
        <div className="navbar-logo-icon"><Shield size={20} /></div>
        <div className="navbar-logo-text">
          <span className="navbar-logo-title">ContratosVertiche</span>
          <span className="navbar-logo-sub">Compliance legal</span>
        </div>
      </div>

      <nav className="navbar-nav">
        <span className="navbar-section-label">Principal</span>
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end className={({ isActive }) => `navbar-link ${isActive ? "active" : ""}`}>
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="navbar-footer">
        <NavLink to="/monitoreo" className="navbar-link">
          <Bell size={18} />
          <span>Prueba WhatsApp/Teams</span>
        </NavLink>
      </div>
    </aside>
  );
}
