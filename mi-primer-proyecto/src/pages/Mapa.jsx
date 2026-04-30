// Nota: Asegúrate de tener instalado: npm install react-leaflet leaflet
// Y agrega este import en tu main.jsx o index.css:
// import 'leaflet/dist/leaflet.css'

import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import { useNavigate } from "react-router-dom";
import { sucursales } from "../data/mockData";
import { MapPin, AlertTriangle, FileText, TrendingUp } from "lucide-react";
import "leaflet/dist/leaflet.css";

function scoreColor(score) {
  if (score >= 80) return "#00D4AA";
  if (score >= 55) return "#F59E0B";
  return "#EF4444";
}

function SucursalPopup({ sucursal, onDetalle }) {
  return (
    <div className="mapa-popup">
      <h3 className="popup-nombre">{sucursal.nombre}</h3>
      <p className="popup-estado">{sucursal.estado}</p>
      <div className="popup-stats">
        <div className="popup-stat">
          <FileText size={14} />
          <span>{sucursal.tramitesActivos} trámites</span>
        </div>
        <div className="popup-stat">
          <AlertTriangle size={14} />
          <span>{sucursal.alertas} alertas</span>
        </div>
        <div className="popup-stat">
          <TrendingUp size={14} />
          <span style={{ color: scoreColor(sucursal.score) }}>
            Score: {sucursal.score}%
          </span>
        </div>
      </div>
      <button
        className="popup-btn"
        onClick={() => onDetalle(sucursal.id)}
      >
        Ver detalle →
      </button>
    </div>
  );
}

export default function Mapa() {
  const navigate = useNavigate();

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Mapa de Sucursales</h1>
          <p className="page-sub">
            Haz clic en una sucursal para ver el detalle de sus trámites
          </p>
        </div>
        <div className="leyenda">
          <span className="leyenda-item">
            <span className="leyenda-dot" style={{ background: "#00D4AA" }} />
            Buen estado (≥80%)
          </span>
          <span className="leyenda-item">
            <span className="leyenda-dot" style={{ background: "#F59E0B" }} />
            Atención (55–79%)
          </span>
          <span className="leyenda-item">
            <span className="leyenda-dot" style={{ background: "#EF4444" }} />
            Crítico (&lt;55%)
          </span>
        </div>
      </div>

      <div className="card mapa-card">
        <MapContainer
          center={[23.6345, -102.5528]}
          zoom={5}
          style={{ height: "520px", width: "100%", borderRadius: "8px" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://carto.com">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          {sucursales.map((s) => (
            <CircleMarker
              key={s.id}
              center={[s.lat, s.lng]}
              radius={14}
              pathOptions={{
                fillColor: scoreColor(s.score),
                fillOpacity: 0.9,
                color: "#fff",
                weight: 2,
              }}
            >
              <Popup>
                <SucursalPopup
                  sucursal={s}
                  onDetalle={(id) => navigate(`/sucursal/${id}`)}
                />
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      {/* Tabla resumen de sucursales */}
      <div className="card">
        <h2 className="card-title">Resumen de Sucursales</h2>
        <div className="tabla-wrap">
          <table className="tabla">
            <thead>
              <tr>
                <th>Sucursal</th>
                <th>Estado</th>
                <th>Trámites Activos</th>
                <th>Alertas</th>
                <th>Score</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sucursales.map((s) => (
                <tr key={s.id}>
                  <td className="td-nombre">
                    <MapPin size={14} />
                    {s.nombre}
                  </td>
                  <td className="td-muted">{s.estado}</td>
                  <td>{s.tramitesActivos}</td>
                  <td>
                    {s.alertas > 0 ? (
                      <span className="badge-alerta alerta-rojo">{s.alertas}</span>
                    ) : (
                      <span className="td-muted">—</span>
                    )}
                  </td>
                  <td>
                    <span style={{ color: scoreColor(s.score), fontWeight: 600 }}>
                      {s.score}%
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn-link"
                      onClick={() => navigate(`/sucursal/${s.id}`)}
                    >
                      Ver detalle →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
