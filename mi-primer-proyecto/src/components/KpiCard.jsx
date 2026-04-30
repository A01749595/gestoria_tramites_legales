import {
  FileText,
  Clock,
  AlertTriangle,
  CheckCircle,
  Bell,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

const iconMap = {
  FileText,
  Clock,
  AlertTriangle,
  CheckCircle,
  Bell,
  TrendingUp,
};

export default function KpiCard({ titulo, valor, cambio, unidad, icono, color }) {
  const Icon = iconMap[icono] || FileText;
  const positivo = cambio >= 0;

  // Para KPIs negativos (vencidos, por vencer), subir es malo
  const esMalo = ["amber", "red"].includes(color);
  const esPositivo = esMalo ? !positivo : positivo;

  return (
    <div className={`kpi-card kpi-${color}`}>
      <div className="kpi-header">
        <span className="kpi-titulo">{titulo}</span>
        <div className={`kpi-icon-wrap kpi-icon-${color}`}>
          <Icon size={18} />
        </div>
      </div>
      <div className="kpi-valor">
        {valor}
        {unidad && <span className="kpi-unidad">{unidad}</span>}
      </div>
      <div className={`kpi-cambio ${esPositivo ? "positivo" : "negativo"}`}>
        {esPositivo ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
        <span>
          {positivo ? "+" : ""}
          {cambio} vs mes anterior
        </span>
      </div>
    </div>
  );
}
