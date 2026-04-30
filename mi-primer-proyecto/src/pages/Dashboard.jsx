import { kpis, datosGrafico, alertasRecientes } from "../data/mockData";
import KpiCard from "../components/KpiCard";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Bell, MapPin } from "lucide-react";
import { useNavigate } from "react-router-dom";

const alertaTipoConfig = {
  vencido: { label: "Vencido", class: "alerta-rojo" },
  por_vencer: { label: "Por vencer", class: "alerta-amber" },
  incompleto: { label: "Incompleto", class: "alerta-blue" },
};

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">Resumen general de trámites y cumplimiento</p>
        </div>
        <button className="btn-primary" onClick={() => navigate("/mapa")}>
          <MapPin size={16} />
          Ver Mapa de Sucursales
        </button>
      </div>

      {/* KPIs */}
      <div className="kpi-grid">
        {kpis.map((kpi) => (
          <KpiCard key={kpi.id} {...kpi} />
        ))}
      </div>

      {/* Gráfico + Alertas */}
      <div className="dashboard-grid">
        {/* Gráfico */}
        <div className="card">
          <h2 className="card-title">Trámites por Mes</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={datosGrafico} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2d3d" />
              <XAxis dataKey="mes" stroke="#64748b" tick={{ fontSize: 12 }} />
              <YAxis stroke="#64748b" tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: "#0f1e2e",
                  border: "1px solid #1e2d3d",
                  borderRadius: "8px",
                  color: "#e2e8f0",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "12px", color: "#94a3b8" }} />
              <Bar dataKey="completados" name="Completados" fill="#00D4AA" radius={[4, 4, 0, 0]} />
              <Bar dataKey="enProceso" name="En Proceso" fill="#3B82F6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="vencidos" name="Vencidos" fill="#EF4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Alertas recientes */}
        <div className="card">
          <div className="card-title-row">
            <h2 className="card-title">Alertas Recientes</h2>
            <Bell size={16} className="icon-muted" />
          </div>
          <div className="alertas-lista">
            {alertasRecientes.map((a) => {
              const cfg = alertaTipoConfig[a.tipo] || alertaTipoConfig.incompleto;
              return (
                <div key={a.id} className="alerta-item">
                  <div className="alerta-left">
                    <span className={`alerta-dot ${cfg.class}`} />
                    <div>
                      <p className="alerta-tramite">{a.tramite}</p>
                      <p className="alerta-sucursal">
                        {a.sucursal} · {a.destinatarios} destinatario
                        {a.destinatarios > 1 ? "s" : ""}
                      </p>
                    </div>
                  </div>
                  <div className="alerta-right">
                    <span className={`badge-alerta ${cfg.class}`}>{cfg.label}</span>
                    <span className="alerta-fecha">{a.fecha}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
