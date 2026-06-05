import {
  FileText,
  Clock,
  AlertTriangle,
  CheckCircle,
  Bell,
  TrendingUp,
  TrendingDown,
  MapPin,
  Building2,
  ShieldCheck,
} from "lucide-react";

const iconMap = {
  FileText,
  Clock,
  AlertTriangle,
  CheckCircle,
  Bell,
  TrendingUp,
  MapPin,
  Building2,
  ShieldCheck,
};

/**
 * KpiCard — tarjeta de indicador clave.
 *
 * Props:
 *  - titulo: nombre del indicador (texto corto).
 *  - valor: número grande mostrado.
 *  - unidad: símbolo o sufijo opcional ("%", "MXN", etc.).
 *  - icono: nombre del icono de lucide-react.
 *  - color: variante de color. Para los KPIs semáforo usa "green" (vigentes),
 *           "amber" (por vencer) y "red" (vencidos). Pinta el borde lateral
 *           y el icono.
 *  - sub: subtítulo opcional debajo del valor (ej. "de 320 documentos").
 *  - cambio: número entero opcional; si se pasa, se muestra "+N vs mes anterior".
 *            Omítelo cuando no se tenga base de comparación.
 */
export default function KpiCard({ titulo, valor, sub, cambio, unidad, icono, color }) {
  const Icon = iconMap[icono] || FileText;
  const hasCambio = typeof cambio === "number" && !Number.isNaN(cambio);
  const positivo = (cambio ?? 0) >= 0;
  // Para KPIs negativos (vencidos, por vencer) subir es malo.
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
      {sub && <div className="kpi-sub">{sub}</div>}
      {hasCambio && (
        <div className={`kpi-cambio ${esPositivo ? "positivo" : "negativo"}`}>
          {esPositivo ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
          <span>
            {positivo ? "+" : ""}
            {cambio} vs mes anterior
          </span>
        </div>
      )}
    </div>
  );
}
