import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Dashboard from "./pages/Dashboard";
import Mapa from "./pages/Mapa";
import Sucursal from "./pages/Sucursal";
import Documentos from "./pages/Documentos";
import Monitoreo from "./pages/Monitoreo";
import Asistente from "./pages/Asistente";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <Navbar />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/mapa" element={<Mapa />} />
            <Route path="/sucursal/:id" element={<Sucursal />} />
            <Route path="/documentos" element={<Documentos />} />
            <Route path="/monitoreo" element={<Monitoreo />} />
            <Route path="/asistente" element={<Asistente />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
