import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import { RefreshCw, MapPin } from "lucide-react";
import KpiCard from "../components/KpiCard";
import { getDashboard } from "../services/api";

const statusLabel = {
  valid: "Vigentes",
  close_to_expiration: "Por vencer",
  expired: "Vencidos",
  incomplete: "Sin fecha",
  missing: "Faltantes",
  unreadable: "No legibles",
};

function number(value) {
  return Number(value || 0).toLocaleString("es-MX");
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(refresh = false) {
    setLoading(true);
    setError("");
    try {
      setData(await getDashboard(refresh));
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No se pudo cargar el dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(false); }, []);

  const overview = data?.overview || {};
  const compliance = data?.compliance_summary || {};
  const docs = data?.data?.documents || [];
  const branches = data?.data?.branches || [];

  const statusChart = useMemo(() => {
    const raw = overview.documents_by_status || {};
    return Object.entries(raw).filter(([, v]) => v > 0).map(([key, value]) => ({ name: statusLabel[key] || key, value }));
  }, [overview]);

  const stateChart = useMemo(() => {
    const states = data?.state_analysis?.states || {};
    return Object.entries(states)
      .map(([state, row]) => ({ state, sucursales: row.branch_count || row.branches?.length || 0, score: row.average_score || 0 }))
      .sort((a, b) => b.sucursales - a.sucursales)
      .slice(0, 10);
  }, [data]);

  const kpis = [
    { titulo: "Sucursales", valor: number(overview.total_branches || branches.length), unidad: "", icono: "FileText", color: "teal", cambio: 0 },
    { titulo: "Documentos", valor: number(overview.total_documents || docs.length), unidad: "", icono: "FileText", color: "blue", cambio: 0 },
    { titulo: "Vencen pronto", valor: number(overview.expiring_soon_count || 0), unidad: "", icono: "Clock", color: "amber", cambio: 0 },
    { titulo: "Vencidos", valor: number(overview.expired_documents || 0), unidad: "", icono: "AlertTriangle", color: "red", cambio: 0 },
    { titulo: "Score promedio", valor: Number(compliance.average_score || 0).toFixed(1), unidad: "%", icono: "TrendingUp", color: "green", cambio: 0 },
  ];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard de cumplimiento</h1>
          <p className="page-sub">Métricas alimentadas por OCR, Supabase, OpenAI y agentes de compliance.</p>
        </div>
        <div className="actions-row">
          <button className="btn-secondary" onClick={() => load(true)} disabled={loading}>
            <RefreshCw size={16} /> Refrescar
          </button>
          <button className="btn-primary" onClick={() => navigate("/mapa")}>
            <MapPin size={16} /> Ver mapa
          </button>
        </div>
      </div>

      {error && <div className="card card-error">{error}</div>}
      {data?.data?.demo && <div className="card card-info">Estás viendo datos demo porque aún falta configurar Supabase/OpenAI o no hay documentos procesados.</div>}
      {loading ? <div className="card">Cargando dashboard...</div> : (
        <>
          <div className="kpi-grid">
            {kpis.map((kpi) => <KpiCard key={kpi.titulo} {...kpi} />)}
          </div>

          <div className="grid-2">
            <div className="card chart-card">
              <h3>Estado de documentos</h3>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={statusChart} dataKey="value" nameKey="name" outerRadius={90} label />
                  {statusChart.map((_, i) => <Cell key={i} />)}
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="card chart-card">
              <h3>Top estados por sucursales</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={stateChart} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="state" width={120} />
                  <Tooltip />
                  <Bar dataKey="sucursales" name="Sucursales" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card">
            <div className="section-title-row"><h3>Detalle de documentos</h3><span className="td-muted">{docs.length} registros</span></div>
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Documento</th><th>Sucursal</th><th>Tipo</th><th>Estado</th><th>Vencimiento</th></tr></thead>
                <tbody>
                  {docs.slice(0, 12).map((doc) => (
                    <tr key={doc.document_id}>
                      <td>{doc.document_name}</td>
                      <td>{doc.branch_id}</td>
                      <td>{doc.document_type}</td>
                      <td><span className={`badge status-${doc.status}`}>{statusLabel[doc.status] || doc.status}</span></td>
                      <td>{doc.expiration_date || "Sin fecha"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
