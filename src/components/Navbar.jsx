import { NavLink, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { jwtDecode } from "jwt-decode";
import { 
  LayoutDashboard, 
  Map, 
  FolderOpen, 
  Bell,
  Shield, 
  Bot, 
  Activity, 
  ClipboardList, 
  LogOut, 
  User 
} from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/documentos", label: "Documentos", icon: FolderOpen },
  { to: "/monitoreo", label: "Alertas", icon: Bell },
  { to: "/asistente", label: "Asistente IA", icon: Bot },
];

export default function Navbar() {
  const { token, logout } = useAuth();
  const navigate = useNavigate();
  const [userEmail, setUserEmail] = useState("Usuario");

  // 🛡️ SEGURIDAD: Si no hay token, bota al usuario al Login inmediatamente
  /*useEffect(() => {
    if (!token) {
      navigate("/login"); // Reemplaza por la ruta exacta de tu Login si es diferente
    } else {
      try {
        // Decodificamos el token para extraer el email del usuario logueado
        const decoded = jwtDecode(token);
        if (decoded && decoded.sub) {
          setUserEmail(decoded.sub);
        }
      } catch (error) {
        console.error("Error al decodificar el token:", error);
        logout();
        navigate("/login");
      }
    }
  }, [token, navigate, logout]);*/

  // 🛡️ SEGURIDAD: Si no hay token, dejamos que App.jsx maneje el bloqueo
  useEffect(() => {
    if (token) {
      try {
        const decoded = jwtDecode(token);
        if (decoded && decoded.sub) {
          setUserEmail(decoded.sub);
        }
      } catch (error) {
        console.error("Error al decodificar el token:", error);
        logout();
      }
    }
  }, [token, logout]);

  const handleLogout = () => {
    if (window.confirm("¿Estás seguro de que deseas cerrar sesión?")) {
      logout(); // Al ejecutar esto, token pasa a ser null. 
                // App.jsx lo detectará al instante y desmontará todo para poner el Login.
    }
  };

  return (
    <aside className="navbar">
      <div className="navbar-logo">
        <div className="navbar-logo-icon"><Shield size={20} /></div>
        <div className="navbar-logo-text">
          <span className="navbar-logo-title">GESTIO</span>
          <span className="navbar-logo-sub">Compliance Control</span>
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

      {/* 👤 SECCIÓN INFERIOR: PERFIL Y CERRAR SESIÓN */}
      <div className="navbar-footer" style={{ marginTop: "auto", padding: "1rem 0", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        
        {/* Botón de Perfil (Muestra el correo) */}
        <div className="navbar-link" style={{ cursor: "default", color: "var(--text-muted, #bdcae5)", display: "flex", alignItems: "center", gap: "10px", padding: "0.5rem 1rem" }}>
          <User size={18} style={{ color: "var(--primary-color, #bdcae5)" }} />
          <span style={{ fontSize: "0.85rem", textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }} title={userEmail}>
            {userEmail}
          </span>
        </div>

        {/* Botón de Cerrar Sesión */}
        <button 
          onClick={handleLogout}
          className="navbar-link" 
          style={{ 
            width: "100%", 
            background: "none", 
            border: "none", 
            textAlign: "left", 
            cursor: "pointer", 
            display: "flex", 
            alignItems: "center", 
            gap: "10px",
            color: "#ffffff", 
            padding: "0.5rem 1rem"
          }}
        >
          <LogOut size={18} />
          <span>Cerrar Sesión</span>
        </button>

      </div>
    </aside>
  );
}