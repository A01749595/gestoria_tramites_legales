import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, AlertTriangle, FileText, MapPin } from "lucide-react";
import { getDashboard } from "../services/api";

const statusLabel = { valid: "Vigente", close_to_expiration: "Por vencer", expired: "Vencido", incomplete: "Sin fecha" };

export default function Sucursal() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  useEffect(() => { getDashboard(false).then(setData); }, []);

  const branch = useMemo(() => (data?.data?.branches || []).find((b) => b.branch_id === id), [data, id]);
  const docs = useMemo(() => (data?.data?.documents || []).filter((d) => d.branch_id === id), [data, id]);
  const score = data?.data?.compliance_scores?.[id] || 0;

  if (!data) return <div className="page"><div className="card">Cargando sucursal...</div></div>;
  if (!branch) return <div className="page"><button className="btn-back" onClick={() => navigate("/mapa")}><ArrowLeft size={16} /> Volver</button><div className="card">Sucursal no encontrada.</div></div>;

  const vencidos = docs.filter((d) => d.status === "expired").length;
  const porVencer = docs.filter((d) => d.status === "close_to_expiration").length;

  return (
    <div className="page">
      <button className="btn-back" onClick={() => navigate("/mapa")}><ArrowLeft size={16} /> Volver al mapa</button>
      <div className="page-header">
        <div>
          <div className="sucursal-titulo-row"><MapPin size={18} className="icon-teal" /><h1 className="page-title">{branch.branch_name}</h1></div>
          <p className="page-sub">{branch.state} · {branch.municipality}</p>
        </div>
        <div className="score-pill">Score {score}%</div>
      </div>

      <div className="sucursal-stats">
        <div className="stat-pill"><FileText size={15} /> {docs.length} documentos</div>
        <div className="stat-pill stat-red"><AlertTriangle size={15} /> {vencidos} vencidos</div>
        <div className="stat-pill stat-amber">{porVencer} por vencer</div>
      </div>

      <div className="card">
        <h3>Documentos de la sucursal</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Documento</th><th>Tipo</th><th>Estado</th><th>Vencimiento</th><th>Folio</th></tr></thead>
            <tbody>{docs.map((d) => <tr key={d.document_id}><td>{d.document_name}</td><td>{d.document_type}</td><td><span className={`badge status-${d.status}`}>{statusLabel[d.status] || d.status}</span></td><td>{d.expiration_date || "Sin fecha"}</td><td>{d.folio_number || "—"}</td></tr>)}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
