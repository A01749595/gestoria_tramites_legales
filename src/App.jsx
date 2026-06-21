import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import LoginForm from './components/LoginForm';

// Importaciones de tus componentes actuales
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import Sucursal from './pages/Sucursal';
import Documentos from './pages/Documentos';
import Monitoreo from './pages/Monitoreo';
import Asistente from './pages/Asistente';

function MainApp() {
  const auth = useAuth(); // 👈 Leemos el contexto completo primero

  // 🛡️ PROTECCIÓN CRÍTICA: Si el contexto aún es null o se está cargando,
  // evitamos que la app explote devolviendo una pantalla de carga temporal.
  if (!auth) {
    return <div style={{ padding: "20px", textFamily: "sans-serif" }}>Cargando aplicación...</div>;
  }

  // Ahora que estamos 100% seguros de que 'auth' existe, extraemos el token de forma segura
  const { token } = auth;

  // 1. Si NO hay token, el enrutador solo renderizará el Login
  if (!token) {
    return (
      <Routes>
        <Route path="*" element={<LoginForm />} />
      </Routes>
    );
  }

  // 2. Si SÍ hay token, se monta la estructura completa de tu Dashboard
  return (
    <div className="app-layout">
      <Navbar />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sucursal/:id" element={<Sucursal />} />
          <Route path="/documentos" element={<Documentos />} />
          <Route path="/monitoreo" element={<Monitoreo />} />
          <Route path="/asistente" element={<Asistente />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

// 📦 El componente principal que exportas SIEMPRE debe envolver a MainApp
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <MainApp />
      </AuthProvider>
    </BrowserRouter>
  );
}
