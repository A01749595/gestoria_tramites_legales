import { FileText, Calendar, User, AlertCircle } from "lucide-react";

const estatusConfig = {
  vigente: { label: "Vigente", class: "estatus-vigente" },
  en_proceso: { label: "En Proceso", class: "estatus-proceso" },
  vencido: { label: "Vencido", class: "estatus-vencido" },
};

const tipoLabel = {
  renovacion: "Renovación",
  obtencion: "Obtención",
};

function ScoreBar({ score, estatus }) {
  if (estatus === "vigente") return null;

  const color =
    score >= 75 ? "#00D4AA" : score >= 40 ? "#F59E0B" : "#EF4444";

  return (
    <div className="score-wrap">
      <div className="score-header">
        <span className="score-label">Progreso</span>
        <span className="score-val" style={{ color }}>
          {score}%
        </span>
      </div>
      <div className="score-bar-bg">
        <div
          className="score-bar-fill"
          style={{ width: `${score}%`, background: color }}
        />
      </div>
    </div>
  );
}

export default function TramiteCard({ tramite }) {
  const { nombre, tipo, estatus, score, vencimiento, responsable, documentosFaltantes } =
    tramite;
  const cfg = estatusConfig[estatus] || estatusConfig.vigente;

  const fechaFormateada = new Date(vencimiento).toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  return (
    <div className={`tramite-card ${estatus === "vencido" ? "tramite-vencido" : ""}`}>
      <div className="tramite-header">
        <div className="tramite-nombre-wrap">
          <FileText size={15} className="tramite-icon" />
          <span className="tramite-nombre">{nombre}</span>
        </div>
        <div className="tramite-badges">
          <span className="badge-tipo">{tipoLabel[tipo]}</span>
          <span className={`badge-estatus ${cfg.class}`}>{cfg.label}</span>
        </div>
      </div>

      <ScoreBar score={score} estatus={estatus} />

      <div className="tramite-meta">
        <span className="tramite-meta-item">
          <Calendar size={13} />
          {fechaFormateada}
        </span>
        <span className="tramite-meta-item">
          <User size={13} />
          {responsable}
        </span>
        {documentosFaltantes > 0 && (
          <span className="tramite-meta-item alerta">
            <AlertCircle size={13} />
            {documentosFaltantes} doc{documentosFaltantes > 1 ? "s" : ""} faltante
            {documentosFaltantes > 1 ? "s" : ""}
          </span>
        )}
      </div>
    </div>
  );
}
