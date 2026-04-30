import { useParams, useNavigate } from "react-router-dom";
import { sucursales, tramitesPorSucursal } from "../data/mockData";
import TramiteCard from "../components/TramiteCard";
import { ArrowLeft, MapPin, AlertTriangle, FileText, TrendingUp, Filter } from "lucide-react";
import { useState } from "react";

function ScoreGauge({ score }) {
  const color = score >= 80 ? "#00D4AA" : score >= 55 ? "#F59E0B" : "#EF4444";
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="gauge-wrap">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="40" fill="none" stroke="#1e2d3d" strokeWidth="8" />
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
        <text x="50" y="50" textAnchor="middle" dy="0.35em" fill={color} fontSize="18" fontWeight="700">
          {score}%
        </text>
      </svg>
      <span className="gauge-label">Score General</span>
    </div>
  );
}

export default function Sucursal() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [filtro, setFiltro] = useState("todos");

  const sucursal = sucursales.find((s) => s.id === Number(id));
  const tramites = tramitesPorSucursal[id] || [];

  if (!sucursal) {
    return (
      <div className="page">
        <p className="td-muted">Sucursal no encontrada.</p>
        <button className="btn-secondary" onClick={() => navigate("/mapa")}>
          Volver al mapa
        </button>
      </div>
    );
  }

  const filtrados =
    filtro === "todos"
      ? tramites
      : tramites.filter((t) => t.estatus === filtro);

  const countByEstatus = {
    vigente: tramites.filter((t) => t.estatus === "vigente").length,
    en_proceso: tramites.filter((t) => t.estatus === "en_proceso").length,
    vencido: tramites.filter((t) => t.estatus === "vencido").length,
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="btn-back" onClick={() => navigate("/mapa")}>
            <ArrowLeft size={16} /> Volver al mapa
          </button>
          <div>
            <div className="sucursal-titulo-row">
              <MapPin size={18} className="icon-teal" />
              <h1 className="page-title">{sucursal.nombre}</h1>
            </div>
            <p className="page-sub">{sucursal.estado}</p>
          </div>
        </div>
        <ScoreGauge score={sucursal.score} />
      </div>

      {/* Stats rápidas */}
      <div className="sucursal-stats">
        <div className="stat-pill">
          <FileText size={15} />
          <span>{tramites.length} trámites totales</span>
        </div>
        <div className="stat-pill stat-green">
          <span>{countByEstatus.vigente} vigentes</span>
        </div>
        <div className="stat-pill stat-blue">
          <span>{countByEstatus.en_proceso} en proceso</span>
        </div>
        <div className="stat-pill stat-red">
          <span>{countByEstatus.vencido} vencidos</span>
        </div>
        {sucursal.alertas > 0 && (
          <div className="stat-pill stat-amber">
            <AlertTriangle size={14} />
            <span>{sucursal.alertas} alertas activas</span>
          </div>
        )}
      </div>

      {/* Filtros */}
      <div className="filtros-row">
        <Filter size={15} className="icon-muted" />
        {["todos", "vigente", "en_proceso", "vencido"].map((f) => (
          <button
            key={f}
            className={`filtro-btn ${filtro === f ? "active" : ""}`}
            onClick={() => setFiltro(f)}
          >
            {f === "todos" && "Todos"}
            {f === "vigente" && "Vigentes"}
            {f === "en_proceso" && "En Proceso"}
            {f === "vencido" && "Vencidos"}
          </button>
        ))}
      </div>

      {/* Lista de trámites */}
      <div className="tramites-grid">
        {filtrados.length === 0 ? (
          <p className="td-muted">No hay trámites con este filtro.</p>
        ) : (
          filtrados.map((t) => <TramiteCard key={t.id} tramite={t} />)
        )}
      </div>
    </div>
  );
}
