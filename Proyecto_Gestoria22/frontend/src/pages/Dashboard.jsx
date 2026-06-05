import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import { useNavigate } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  RefreshCw,
  MapPin,
  Building2,
  ShieldCheck,
  AlertTriangle,
  Clock,
  CheckCircle,
  FileText,
  TrendingUp,
  Layers,
  ClipboardList,
  Search,
} from "lucide-react";
import KpiCard from "../components/KpiCard";
import { getDashboard, getTramitesResumen, API_BASE } from "../services/api";

// ──────────────────────────────────────────────────────────────────
// Constantes de color SEMÁFORO. Las leemos del :root del index.css
// para que un solo lugar (CSS) controle la paleta.
// ──────────────────────────────────────────────────────────────────

const COLOR = {
  // ─── SEMAFORIZACIÓN (Estatus de Alerta y Totales) ───
  green: "#5aaf94",     // Verde pastel clínico (contrasta hermoso con texto oscuro)
  amber: "#d6ab4e",     // Amarillo vainilla / arena 
  red: "#a13232",       // Rojo salmón claro
  blue: "#3B82F6",      // Info / Total / Score (Azul moderno e inteligente)
  gray: "#9fa9b7",      // Sin fecha / No legible / "Otros" (Gris neutro limpio)

  // ─── PALETA EXTENDIDA (Para las rebanadas del Gráfico de Anillo / Dona) ───
  // Usa estos colores en orden para tus categorías neutras (Certificados, Contratos, etc.)
  grayblue: "#5e72de", // Categoría principal (Azul Rey)
  indigo: "#7f5ee5",    // Categoría 2 (Índigo premium)
  purple: "#a070c0",    // Categoría 3 (Morado tecnológico)
  teal: "#11a29b",      // Categoría 4 (Teal / Azul verdoso)
  cyan: "#5fbbe6",      // Categoría 5 (Cian / Celeste)
  pink: "#d478a6",      // Categoría 6 (Rosa moderno / Magenta sutil)
  orange: "#e5ac83"     // Categoría 7 (Naranja complementario si tienes muchas áreas)
};

// Mapeo status -> color semáforo. Lo usamos en TODO el dashboard.
const STATUS_COLOR = {
  valid: COLOR.green,
  close_to_expiration: COLOR.amber,
  expired: COLOR.red,
  incomplete: COLOR.gray,
  missing: COLOR.gray,
  unreadable: COLOR.gray,
  pending_review: COLOR.gray,
};

const STATUS_LABEL = {
  valid: "Vigentes",
  close_to_expiration: "Por vencer",
  expired: "Vencidos",
  incomplete: "Sin fecha",
  missing: "Faltantes",
  unreadable: "No legibles",
  pending_review: "Pendientes",
};

// Orden visual fijo para que las leyendas y las barras siempre salgan
// verde -> amber -> rojo -> gris.
const STATUS_ORDER = [
  "valid",
  "close_to_expiration",
  "expired",
  "incomplete",
  "missing",
  "unreadable",
  "pending_review",
];


// Tipos de tramite colores y labels.
const TYPE_COLOR = {
  licencia_funcionamiento: COLOR.teal,
  constancia:              COLOR.indigo,
  permiso:                 COLOR.pink,
  certificado:             COLOR.cyan,
  contrato_arrendamiento:  COLOR.purple,
  factura:                 COLOR.grayblue,
  aviso:                   COLOR.orange,
  otro:                    COLOR.gray,
};

const TYPE_LABEL = {
  licencia_funcionamiento: "Licencia de funcionamiento",
  contrato_arrendamiento:  "Contrato arrendamiento",
  permiso:                 "Permiso",
  constancia:              "Constancia",
  certificado:             "Certificado",
  factura:                 "Factura",
  aviso:                   "Aviso",
  otro:                    "Otro",
};

function number(value) {
  return Number(value || 0).toLocaleString("es-MX");
}

// ──────────────────────────────────────────────────────────────────
// Helpers de agregación: derivan tablas/series desde la lista plana
// de `documents` que ya devuelve el backend con branch_state,
// branch_municipality, branch_name y status enriquecidos.
// ──────────────────────────────────────────────────────────────────
function groupByDimension(docs, dim, dimLabel) {
  // dim: "branch_state" | "branch_municipality" | "branch_name"
  // dimLabel es lo que mostramos cuando la dimensión viene vacía.
  const out = new Map();
  for (const d of docs) {
    const key = d[dim] || dimLabel;
    if (!out.has(key)) {
      out.set(key, {
        name: key,
        total: 0,
        valid: 0,
        close_to_expiration: 0,
        expired: 0,
        incomplete: 0,
        missing: 0,
        unreadable: 0,
        pending_review: 0,
        sucursales: new Set(),
      });
    }
    const row = out.get(key);
    row.total += 1;
    row[d.status] = (row[d.status] || 0) + 1;
    if (d.branch_id) row.sucursales.add(d.branch_id);
  }
  // Materializa el Set de sucursales y calcula compliance %.
  return Array.from(out.values())
    .map((row) => ({
      ...row,
      sucursales: row.sucursales.size,
      compliance:
        row.total > 0
          ? Math.round(
              (100 * (row.valid + 0.5 * row.close_to_expiration)) / row.total,
            )
          : 0,
    }))
    .sort((a, b) => b.total - a.total);
}

function statusPieData(docs) {
  // Conteo absoluto por status para el gráfico de dona.
  const counts = {};
  for (const d of docs) counts[d.status] = (counts[d.status] || 0) + 1;
  return STATUS_ORDER
    .filter((s) => (counts[s] || 0) > 0)
    .map((s) => ({ name: STATUS_LABEL[s], value: counts[s], status: s }));
}

function typePieData(docs) {
  // Conteo por tipo de documento para el gráfico de dona.
  const counts = {};
  for (const d of docs) {
    const t = d.document_type || "otros";
    counts[t] = (counts[t] || 0) + 1;
  }
  return Object.entries(counts)
    .map(([type, value]) => ({
      name: TYPE_LABEL[type] || type,
      value,
      type,
    }))
    .sort((a, b) => b.value - a.value);
}

// ──────────────────────────────────────────────────────────────────
// Componente principal
// ──────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate(); 
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ingestStatus, setIngestStatus] = useState(null);
  const pollRef = useRef(null);

  async function fetchStatus() {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  async function load(refresh = false) {
    setLoading(true);
    setError("");
    try {
      setData(await getDashboard(refresh));
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err.message ||
          "No se pudo cargar el dashboard",
      );
    } finally {
      setLoading(false);
    }
  }

  // Polling del backend mientras la ingesta termina.
  useEffect(() => {
    let stop = false;
    async function tick() {
      const s = await fetchStatus();
      if (stop) return;
      setIngestStatus(s);
      const phase = s?.phase;
      //if (phase === "ready") {
      if (phase === "ready" || (phase === "ocr" && s?.finished_at)) {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        load(false);
      } else if (phase === "error") {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        setLoading(false);
      }
    }
    tick();
    pollRef.current = setInterval(tick, 2500);
    return () => {
      stop = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ── Datos derivados ──
  const overview = data?.overview || {};
  const compliance = data?.compliance_summary || {};
  const docs = data?.data?.documents || [];
  const branches = data?.data?.branches || [];
  const ocrStats = data?.data?.ocr_stats || {};
  const totalPdfs = data?.data?.total_pdfs || 0;

  // Conteos globales por status (vienen del backend pero también los
  // derivamos en frontend para tener consistencia con las dimensiones).
  const totalDocs = docs.length || overview.total_documents || 0;
  const byStatus = useMemo(() => {
    const out = { valid: 0, close_to_expiration: 0, expired: 0, incomplete: 0,
                  missing: 0, unreadable: 0, pending_review: 0 };
    for (const d of docs) out[d.status] = (out[d.status] || 0) + 1;
    return out;
  }, [docs]);

  // pieData ya no se usa — la dona ahora muestra tipos de documento

  // Año en curso: si el backend marcó docs con metadata.folder_year=2026,
  // los contamos aparte para mostrarlos como KPI prioritario.
  const docsFolder2026 = useMemo(
    () => docs.filter((d) => (d.metadata?.folder_year) === 2026),
    [docs],
  );

  // KPIs principales en orden semáforo:
  // Total → Vigentes (verde) → Por vencer (amber) → Vencidos (rojo).
  const kpis = useMemo(
    () => [
      {
        titulo: "Documentos totales",
        valor: number(totalDocs),
        sub: `${number(branches.length || overview.total_branches || 0)} sucursales`,
        icono: "FileText",
        color: "blue",
      },
      {
        titulo: "Vigentes",
        valor: number(byStatus.valid),
        sub: totalDocs ? `${Math.round((100 * byStatus.valid) / totalDocs)}% del total` : "—",
        icono: "CheckCircle",
        color: "green",
      },
      {
        titulo: "Por vencer (≤45 días)",
        valor: number(byStatus.close_to_expiration),
        sub: totalDocs ? `${Math.round((100 * byStatus.close_to_expiration) / totalDocs)}% del total` : "—",
        icono: "Clock",
        color: "amber",
      },
      {
        titulo: "Vencidos",
        valor: number(byStatus.expired),
        sub: totalDocs ? `${Math.round((100 * byStatus.expired) / totalDocs)}% del total` : "—",
        icono: "AlertTriangle",
        color: "red",
      },
      {
        titulo: "Score de cumplimiento",
        valor: Number(compliance.average_score || 0).toFixed(1),
        unidad: "%",
        sub: `${number(compliance.compliant_branches || 0)} sucursales OK · ${number(compliance.at_risk_branches || 0)} en riesgo`,
        icono: "ShieldCheck",
        color: "teal",
      },
      {
        titulo: "En carpeta 2026",
        valor: number(docsFolder2026.length),
        sub: "Año prioritario del proyecto",
        icono: "TrendingUp",
        color: "purple",
      },
    ],
    [byStatus, totalDocs, compliance, branches.length, overview.total_branches, docsFolder2026.length],
  );

  const ingestBusy =
    //ingestStatus && !["ready", "error", "idle"].includes(ingestStatus.phase);
    ingestStatus && !["ready", "error", "idle"].includes(ingestStatus.phase) && !ingestStatus.finished_at;
  const ingestErr = ingestStatus?.phase === "error" ? ingestStatus.error : null;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">
            Controla el cumplimiento de tus sucursales con esta vista general de KPIs, gráficos y mapa interactivo. 
          </p>
        </div>
        <div className="actions-row">
          <button
            className="btn-secondary"
            onClick={() => load(true)}
            disabled={loading || ingestBusy}
          >
            <RefreshCw size={16} /> Refrescar
          </button>
        </div>
      </div>

      {ingestBusy && (
        <div className="card card-info">
          <strong>Procesando documentos en el backend...</strong>{" "}
          {ingestStatus.message}
          {ingestStatus.total > 0 && (
            <>
              {" "}({ingestStatus.processed} / {ingestStatus.total}
              {" — "}
              {Math.round(
                (100 * (ingestStatus.processed || 0)) /
                  Math.max(1, ingestStatus.total),
              )}
              %)
            </>
          )}
          <div style={{ marginTop: 6, fontSize: 13, opacity: 0.8 }}>
            Los KPIs y gráficos aparecerán automáticamente cuando termine.
          </div>
        </div>
      )}
      {ingestErr && <div className="card card-error">Backend: {ingestErr}</div>}
      {error && <div className="card card-error">{error}</div>}
      {data?.data?.demo && !ingestBusy && (
        <div className="card card-info">
          Estás viendo datos demo porque aún falta configurar Supabase/OpenAI o no hay
          documentos procesados.
        </div>
      )}

      {(loading || ingestBusy) ? (
        <div className="card">
          {ingestBusy
            ? "Esperando a que termine el procesamiento OCR para mostrar las métricas..."
            : "Cargando dashboard..."}
        </div>
      ) : (
        <>
          {/* ─── KPIs principales ─── */}
          <div className="kpi-grid">
            {kpis.map((kpi) => (
              <KpiCard key={kpi.titulo} {...kpi} />
            ))}
          </div>

          {/* ─── Contenido principal ─── */}
          <ResumenView
            docs={docs}
            ocrStats={ocrStats}
            totalPdfs={totalPdfs}
            branches={branches}
            scores={data?.data?.compliance_scores || {}}
            navigate={navigate}
          />
        </>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Vista principal: dona + barras + mapa
// ──────────────────────────────────────────────────────────────────
function ResumenView({ docs, ocrStats, totalPdfs, branches, scores, navigate }) {
  const typePie = useMemo(() => typePieData(docs), [docs]);

  const stateStacked = useMemo(() => {
    const rows = groupByDimension(docs, "branch_state", "Sin estado").slice(0, 10);
    return rows;
  }, [docs]);

  // Puntos del mapa
  const COORDS = {
    "Ciudad de México": [19.43,-99.13], "Nuevo León": [25.69,-100.32],
    "Jalisco": [20.66,-103.35],         "Puebla": [19.04,-98.20],
    "Baja California": [32.50,-117.04], "Yucatán": [20.97,-89.62],
    "Guanajuato": [21.02,-101.26],      "México": [19.35,-99.65],
    "Querétaro": [20.59,-100.39],       "Veracruz": [19.17,-96.13],
    "Chihuahua": [28.63,-106.07],       "Sonora": [29.07,-110.96],
    "Coahuila": [25.42,-101.01],        "Sinaloa": [24.81,-107.39],
    "Oaxaca": [17.07,-96.73],           "Guerrero": [17.55,-99.50],
    "Michoacán": [19.70,-101.19],       "Morelos": [18.68,-99.10],
    "Tlaxcala": [19.32,-98.24],         "Hidalgo": [20.09,-98.76],
    "Quintana Roo": [21.16,-86.85],     "Tamaulipas": [24.27,-98.84],
  };

  function scoreColor(s) {
    return s >= 80 ? COLOR.green : s >= 50 ? COLOR.amber : COLOR.red;
  }

  /*const mapPoints = useMemo(() =>
    branches.map((b, i) => {
      const base = COORDS[b.state] || [23.63,-102.55];
      const score = scores[b.branch_id] || 0;
      const branchDocs = docs.filter((d) => d.branch_id === b.branch_id);
      return {
        ...b,
        lat: base[0] + (i % 7) * 0.05,
        lng: base[1] + (i % 7) * 0.05,
        score,
        total: branchDocs.length,
        vencidos: branchDocs.filter((d) => d.status === "expired").length,
      };
    }),
  [branches, scores, docs]);*/
  
  const resolvedBranches = useMemo(() => {
  const map = new Map();
  for (const b of branches) {
    if (!b.branch_id) continue;
    map.set(b.branch_id, {
      branch_id:    b.branch_id,
      name:         b.branch_name || b.name || b.branch_id,
      state:        b.state || b.branch_state || "",
      municipality: b.municipality || b.branch_municipality || "",
    });
  }
  for (const d of docs) {
    if (!d.branch_id) continue;
    if (!map.has(d.branch_id)) {
      map.set(d.branch_id, {
        branch_id:    d.branch_id,
        name:         d.branch_name || d.branch_id,
        state:        d.branch_state || "",
        municipality: d.branch_municipality || "",
      });
    } else {
      const ex = map.get(d.branch_id);
      if (!ex.state && d.branch_state)               ex.state        = d.branch_state;
      if (!ex.municipality && d.branch_municipality) ex.municipality = d.branch_municipality;
      if (!ex.name && d.branch_name)                 ex.name         = d.branch_name;
    }
  }
  return Array.from(map.values());
}, [branches, docs]);

const mapPoints = useMemo(() =>
  resolvedBranches.map((b, i) => {
    const base  = COORDS[b.state] || [23.63, -102.55];
    const score = scores[b.branch_id] || 0;
    const bdocs = docs.filter((d) => d.branch_id === b.branch_id);
    return {
      ...b,
      lat:      base[0] + (i % 7) * 0.06,
      lng:      base[1] + (i % 7) * 0.06,
      score,
      total:    bdocs.length,
      vencidos: bdocs.filter((d) => d.status === "expired").length,
    };
  }),
[resolvedBranches, scores, docs]);


  return (
    <>
      <div className="grid-2">
        <div className="card chart-card">
          <h3>Tipos de documentos</h3>
          <p className="td-muted" style={{ marginTop: -6 }}>
            Distribución global por tipo de trámite.
          </p>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={typePie}
                dataKey="value"
                nameKey="name"
                innerRadius={55}
                outerRadius={95}
                paddingAngle={2}
                label={(e) => `${e.value}`}
              >
                {typePie.map((entry, i) => (
                  <Cell key={i} fill={TYPE_COLOR[entry.type] || COLOR.gray} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value, name) => [number(value), name]}
                contentStyle={{ borderRadius: 8 }}
              />
              <Legend
                verticalAlign="bottom"
                iconType="circle"
                wrapperStyle={{ fontSize: 12 }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h3>Top 10 estados — vigencia apilada</h3>
          <p className="td-muted" style={{ marginTop: -6 }}>
            Por cada estado, cuántos documentos están vigentes, por vencer o vencidos.
          </p>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={stateStacked} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#cde7e6" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
              <Tooltip contentStyle={{ borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="valid" name="Vigentes" stackId="a" fill={COLOR.green} />
              <Bar dataKey="close_to_expiration" name="Por vencer" stackId="a" fill={COLOR.amber} />
              <Bar dataKey="expired" name="Vencidos" stackId="a" fill={COLOR.red} />
              <Bar dataKey="incomplete" name="Sin fecha" stackId="a" fill={COLOR.gray} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Mapa inline */}
      {mapPoints.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "16px 20px 10px", borderBottom: "1px solid var(--border, #e5e7eb)" }}>
            <h3 style={{ margin: 0 }}>Mapa de sucursales</h3>
            <p className="td-muted" style={{ margin: "2px 0 0" }}>
              Haz clic en un marcador para ver el detalle de esa sucursal.
            </p>
          </div>
          <MapContainer
            center={[23.63, -102.55]}
            zoom={5}
            style={{ height: 480, width: "100%" }}
          >
            <TileLayer
              attribution="&copy; CARTO"
              url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
            />
            {mapPoints.map((p) => (
              <CircleMarker
                key={p.branch_id}
                center={[p.lat, p.lng]}
                radius={12}
                pathOptions={{
                  fillColor: scoreColor(p.score),
                  fillOpacity: 0.88,
                  color: "#fff",
                  weight: 1.5,
                }}
              >
                <Popup>
                  <div style={{ minWidth: 160 }}>
                    {/* 🧠 CORRECCIÓN 1: Cambiamos p.branch_name por p.name */}
                    <strong style={{ fontSize: 13 }}>{p.name}</strong>
                    <p style={{ margin: "2px 0 8px", fontSize: 11, color: "#6b7280" }}>
                      {p.state}{p.municipality ? ` · ${p.municipality}` : ""}
                    </p>
                    <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 12 }}>
                      <span>{p.total} documentos</span>
                      <span>{p.vencidos} vencidos</span>
                      <span style={{ color: scoreColor(p.score), fontWeight: 700 }}>
                        Score: {p.score}%
                      </span>
                    </div>
                  </div>
                  
                  {/* 🧠 CORRECCIÓN 2: Regresamos el onClick con el navigate de React Router */}
                  <button 
                    onClick={() => {
                      console.log("ID enviado:", p.branch_id); // Para que revises en F12 si el ID existe
                      navigate(`/sucursal/${p.branch_id}`);
                    }}
                    style={{
                      marginTop: 10, width: "100%", padding: "6px 10px",
                      borderRadius: 4, background: "#e6ecfa", color: "#4b6ee1",
                      border: "1px solid #8995ce", fontSize: 12,
                      fontWeight: 600, cursor: "pointer",
                    }}
                  >
                    Ver detalle →
                  </button>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
          <div style={{ padding: "10px 20px", display: "flex", gap: 20, fontSize: 12, color: "#6b7280" }}>
            {[["#01a085","Bueno (≥80%)"],["#edaa00","Atención (55-79%)"],["#9d1333","Crítico (<55%)"]].map(([c,l]) => (
              <span key={l} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: c, display: "inline-block" }} />
                {l}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// ──────────────────────────────────────────────────────────────────
// Vista "Por dimensión": estado, municipio o sucursal.
// Misma estructura, distinto agrupador.
// ──────────────────────────────────────────────────────────────────
function DimensionView({ docs, dim, emptyLabel, titleLabel }) {
  const rows = useMemo(() => groupByDimension(docs, dim, emptyLabel), [docs, dim, emptyLabel]);
  const [selected, setSelected] = useState(null);

  // Si la dimensión seleccionada cambia o no hay seleccionado, agarra el
  // primero. Útil cuando el usuario llega por primera vez al tab.
  useEffect(() => {
    if (rows.length && (!selected || !rows.find((r) => r.name === selected))) {
      setSelected(rows[0].name);
    }
  }, [rows, selected]);

  const selectedRow = rows.find((r) => r.name === selected);
  const selectedDocs = useMemo(
    () => (selectedRow ? docs.filter((d) => (d[dim] || emptyLabel) === selectedRow.name) : []),
    [docs, dim, emptyLabel, selectedRow],
  );

  // Limitamos la barra principal a 12 ítems para que sea legible;
  // si hay más, los demás se ven en la tabla.
  const chartRows = rows.slice(0, 12);

  const subKpis = selectedRow
    ? [
        {
          titulo: `Documentos en ${selectedRow.name}`,
          valor: number(selectedRow.total),
          sub: `${selectedRow.sucursales} sucursal(es)`,
          icono: "FileText",
          color: "blue",
        },
        {
          titulo: "Vigentes",
          valor: number(selectedRow.valid),
          sub: selectedRow.total
            ? `${Math.round((100 * selectedRow.valid) / selectedRow.total)}%`
            : "—",
          icono: "CheckCircle",
          color: "green",
        },
        {
          titulo: "Por vencer",
          valor: number(selectedRow.close_to_expiration),
          icono: "Clock",
          color: "amber",
        },
        {
          titulo: "Vencidos",
          valor: number(selectedRow.expired),
          icono: "AlertTriangle",
          color: "red",
        },
        {
          titulo: "Cumplimiento estimado",
          valor: `${selectedRow.compliance}`,
          unidad: "%",
          sub: "vigentes + ½ por vencer",
          icono: "ShieldCheck",
          color: "teal",
        },
      ]
    : [];

  return (
    <>
      <div className="card chart-card">
        <h3>Documentos por {titleLabel.toLowerCase()}</h3>
        <p className="td-muted" style={{ marginTop: -6 }}>
          Top {chartRows.length} con la cuenta apilada por estado del documento.
          Haz click en una barra para ver el detalle.
        </p>
        <ResponsiveContainer width="100%" height={Math.max(260, chartRows.length * 28)}>
          <BarChart
            data={chartRows}
            layout="vertical"
            margin={{ left: 20 }}
            onClick={(e) => {
              if (e && e.activeLabel) setSelected(e.activeLabel);
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#cde7e6" />
            <XAxis type="number" allowDecimals={false} />
            <YAxis type="category" dataKey="name" width={160} tick={{ fontSize: 12 }} />
            <Tooltip contentStyle={{ borderRadius: 8 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="valid" name="Vigentes" stackId="a" fill={COLOR.green} />
            <Bar dataKey="close_to_expiration" name="Por vencer" stackId="a" fill={COLOR.amber} />
            <Bar dataKey="expired" name="Vencidos" stackId="a" fill={COLOR.red} />
            <Bar dataKey="incomplete" name="Sin fecha" stackId="a" fill={COLOR.gray} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {selectedRow && (
        <>
          <div className="kpi-grid">
            {subKpis.map((k) => (
              <KpiCard key={k.titulo} {...k} />
            ))}
          </div>
          <DocsTable docs={selectedDocs} limit={50} title={`Detalle: ${selectedRow.name}`} />
        </>
      )}

      <div className="card">
        <div className="section-title-row">
          <h3>Resumen completo por {titleLabel.toLowerCase()}</h3>
          <span className="td-muted">{rows.length} {titleLabel.toLowerCase()}(s)</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{titleLabel}</th>
                <th>Sucursales</th>
                <th>Total</th>
                <th>Vigentes</th>
                <th>Por vencer</th>
                <th>Vencidos</th>
                <th>Sin fecha</th>
                <th>Cumplimiento</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.name}
                  onClick={() => setSelected(r.name)}
                  className={selected === r.name ? "row-selected" : "row-clickable"}
                >
                  <td>{r.name}</td>
                  <td>{r.sucursales}</td>
                  <td>{r.total}</td>
                  <td><span className="badge status-valid">{r.valid}</span></td>
                  <td><span className="badge status-close_to_expiration">{r.close_to_expiration}</span></td>
                  <td><span className="badge status-expired">{r.expired}</span></td>
                  <td>{r.incomplete}</td>
                  <td><ComplianceBar value={r.compliance} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ──────────────────────────────────────────────────────────────────
// Barra de cumplimiento mini: pinta verde/amber/rojo según el valor.
// ──────────────────────────────────────────────────────────────────
function ComplianceBar({ value }) {
  const color = value >= 80 ? COLOR.green : value >= 50 ? COLOR.amber : COLOR.red;
  return (
    <div className="compliance-bar">
      <div className="compliance-bar-fill" style={{ width: `${value}%`, background: color }} />
      <span className="compliance-bar-text">{value}%</span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Tabla de documentos reusable, con buscador integrado.
// Orden de columnas: Documento · Sucursal · Tipo · Estado · Vence · Folio
// (más Ubicación y Conf. OCR como columnas informativas extra).
// ──────────────────────────────────────────────────────────────────
function DocsTable({ docs, limit = 20, title }) {
  const [query, setQuery] = useState("");

  // Filtro de texto libre sobre los campos visibles. Sin acentos para
  // que "merida" encuentre "Mérida".
  const norm = (s) =>
    (s || "")
      .toString()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  const q = norm(query.trim());
  const filtered = useMemo(() => {
    if (!q) return docs;
    return docs.filter((doc) => {
      const haystack = [
        doc.document_name,
        doc.branch_name,
        doc.branch_id,
        doc.branch_state,
        doc.branch_municipality,
        doc.document_type_label,
        doc.document_type,
        doc.status_label,
        STATUS_LABEL[doc.status],
        doc.expiration_date_display,
        doc.expiration_date,
        doc.folio_number,
      ];
      return haystack.some((v) => norm(v).includes(q));
    });
  }, [docs, q]);

  return (
    <div className="card">
      <div className="section-title-row">
        <h3>{title || "Detalle de documentos"}</h3>
        <span className="td-muted">
          {q ? `${filtered.length} de ${docs.length}` : `${docs.length}`} registros
        </span>
      </div>
      <div className="table-search">
        <Search size={15} />
        <input
          className="table-search-input"
          placeholder="Buscar por documento, sucursal, tipo, estado, folio..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {query && (
          <button className="table-search-clear" onClick={() => setQuery("")}>
            Limpiar
          </button>
        )}
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Documento</th>
              <th>Sucursal</th>
              <th>Tipo</th>
              <th>Estado</th>
              <th>Vence</th>
              <th>Folio</th>
              <th>Ubicación</th>
              <th>Conf. OCR</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, limit).map((doc) => {
              const inferred = doc.metadata?.expiration_inferred_from_folder;
              const folderYear = doc.metadata?.folder_year;
              return (
                <tr key={doc.document_id}>
                  <td title={doc.file_url}>{doc.document_name}</td>
                  <td>{doc.branch_name || doc.branch_id}</td>
                  <td>{doc.document_type_label || doc.document_type}</td>
                  <td>
                    <span className={`badge status-${doc.status}`}>
                      {doc.status_label || STATUS_LABEL[doc.status] || doc.status}
                    </span>
                  </td>
                  <td>
                    {doc.expiration_date_display || doc.expiration_date || "Sin fecha"}
                    {inferred && (
                      <span
                        className="inferred-badge"
                        title={`Fecha inferida desde la carpeta ${folderYear}`}
                      >
                        carpeta {folderYear}
                      </span>
                    )}
                  </td>
                  <td>{doc.folio_number || "—"}</td>
                  <td>
                    {[doc.branch_state, doc.branch_municipality].filter(Boolean).join(" · ") || "—"}
                  </td>
                  <td>
                    {doc.ocr_confidence != null
                      ? `${Math.round(doc.ocr_confidence * 100)}%`
                      : "—"}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="td-muted" style={{ textAlign: "center" }}>
                  Sin resultados para "{query}".
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Vista "Trámites por sucursal".
// Lee /api/tramites/resumen: el % de cumplimiento de cada sucursal
// calculado sobre los 5 trámites requeridos (datos del tab de llenado
// manual). Replica el estilo de la vista "Por municipio": KPIs, barras
// apiladas verde/amber/rojo y tabla con buscador.
// ──────────────────────────────────────────────────────────────────
function TramitesView() {
  const [resumen, setResumen] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const r = await getTramitesResumen();
        if (alive) setResumen(r);
      } catch (err) {
        if (alive)
          setError(
            err?.response?.data?.detail || err.message || "No se pudo cargar el resumen de trámites",
          );
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const norm = (s) =>
    (s || "").toString().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

  const sucursales = resumen?.sucursales || [];

  // Seleccionar la primera sucursal al cargar
  useEffect(() => {
    if (sucursales.length && (!selected || !sucursales.find((s) => s.tramite_id === selected))) {
      setSelected(sucursales[0].tramite_id);
    }
  }, [sucursales, selected]);

  const selectedRow = sucursales.find((s) => s.tramite_id === selected);

  const q = norm(query.trim());
  const filtered = useMemo(() => {
    if (!q) return sucursales;
    return sucursales.filter((s) =>
      [s.tramite_id, s.nombre, s.estado, s.municipio].some((v) => norm(v).includes(q)),
    );
  }, [sucursales, q]);

  // Barras ordenadas por % ascendente para que las más críticas estén arriba
  const chartRows = useMemo(
    () =>
      [...filtered]
        .sort((a, b) => a.porcentaje - b.porcentaje)
        .map((s) => ({
          name: `${s.tramite_id} ${s.nombre}`,
          tramite_id: s.tramite_id,
          vigentes: s.vigentes,
          por_vencer: s.por_vencer,
          vencidos: s.vencidos,
          sin_tramite: s.sin_tramite,
          porcentaje: s.porcentaje,
        })),
    [filtered],
  );

  if (loading) return <div className="card">Cargando trámites por sucursal...</div>;
  if (error)   return <div className="card card-error">{error}</div>;

  // KPIs globales (sin selección)
  const kpisGlobales = [
    {
      titulo: "Sucursales con trámites",
      valor: number(resumen.total_sucursales),
      sub: `${resumen.tramites_requeridos?.length || 5} trámites requeridos c/u`,
      icono: "Building2",
      color: "blue",
    },
    {
      titulo: "Cumplimiento promedio",
      valor: `${resumen.promedio_global}`,
      unidad: "%",
      sub: "Promedio sobre vigencia 2026",
      icono: "ShieldCheck",
      color: resumen.promedio_global >= 80 ? "green" : resumen.promedio_global >= 50 ? "amber" : "red",
    },
    {
      titulo: "Sucursales completas",
      valor: number(resumen.sucursales_completas),
      sub: "100% de trámites vigentes",
      icono: "CheckCircle",
      color: "green",
    },
    {
      titulo: "Sucursales en riesgo",
      valor: number(sucursales.filter((s) => s.porcentaje < 50).length),
      sub: "Menos del 50% de cumplimiento",
      icono: "AlertTriangle",
      color: "red",
    },
  ];

  // KPIs de la sucursal seleccionada
  const kpisSeleccionados = selectedRow
    ? [
        {
          titulo: `Trámites en ${selectedRow.nombre}`,
          valor: number((selectedRow.vigentes || 0) + (selectedRow.por_vencer || 0) + (selectedRow.vencidos || 0) + (selectedRow.sin_tramite || 0)),
          sub: `${selectedRow.estado || "—"} · ${selectedRow.municipio || "—"}`,
          icono: "FileText",
          color: "blue",
        },
        {
          titulo: "Vigentes",
          valor: number(selectedRow.vigentes),
          icono: "CheckCircle",
          color: "green",
        },
        {
          titulo: "Por vencer / en trámite",
          valor: number(selectedRow.por_vencer),
          icono: "Clock",
          color: "amber",
        },
        {
          titulo: "Vencidos",
          valor: number(selectedRow.vencidos),
          icono: "AlertTriangle",
          color: "red",
        },
        {
          titulo: "Cumplimiento",
          valor: `${selectedRow.porcentaje}`,
          unidad: "%",
          sub: "vigencia 2026",
          icono: "ShieldCheck",
          color: selectedRow.porcentaje >= 80 ? "green" : selectedRow.porcentaje >= 50 ? "amber" : "red",
        },
      ]
    : [];

  return (
    <>
      <div className="card card-info">
        Estos porcentajes se calculan con los datos capturados en el tab{" "}
        <strong>Trámites (llenado manual)</strong>, evaluando la vigencia 2026 de los 5
        trámites requeridos: {(resumen.tramites_requeridos || []).join(", ")}.
      </div>

      {/* KPIs globales */}
      <div className="kpi-grid">
        {kpisGlobales.map((k) => (
          <KpiCard key={k.titulo} {...k} />
        ))}
      </div>

      {/* Gráfica de barras — click en barra selecciona sucursal */}
      <div className="card chart-card">
        <h3>Cumplimiento de trámites por sucursal</h3>
        <p className="td-muted" style={{ marginTop: -6 }}>
          Las sucursales con menor cumplimiento aparecen arriba. Haz clic en una barra para ver su detalle.
        </p>
        <ResponsiveContainer width="100%" height={Math.max(280, chartRows.length * 30)}>
          <BarChart
            data={chartRows}
            layout="vertical"
            margin={{ left: 30 }}
            onClick={(e) => {
              if (e?.activePayload?.[0]?.payload?.tramite_id) {
                setSelected(e.activePayload[0].payload.tramite_id);
              }
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#cde7e6" />
            <XAxis type="number" allowDecimals={false} />
            <YAxis type="category" dataKey="name" width={180} tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={{ borderRadius: 8 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="vigentes"    name="Vigentes"                stackId="a" fill={COLOR.green} />
            <Bar dataKey="por_vencer"  name="Por vencer / en trámite" stackId="a" fill={COLOR.amber} />
            <Bar dataKey="vencidos"    name="Vencidos"                stackId="a" fill={COLOR.red} />
            <Bar dataKey="sin_tramite" name="Sin trámite / sin dato"  stackId="a" fill={COLOR.gray} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* KPIs de la sucursal seleccionada */}
      {selectedRow && (
        <div className="kpi-grid">
          {kpisSeleccionados.map((k) => (
            <KpiCard key={k.titulo} {...k} />
          ))}
        </div>
      )}

      {/* Tabla con buscador y filas clickeables */}
      <div className="card">
        <div className="section-title-row">
          <h3>Detalle de cumplimiento por sucursal</h3>
          <span className="td-muted">
            {q ? `${filtered.length} de ${sucursales.length}` : sucursales.length} sucursales
          </span>
        </div>
        <div className="table-search">
          <Search size={15} />
          <input
            className="table-search-input"
            placeholder="Buscar por id, nombre, estado o municipio..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button className="table-search-clear" onClick={() => setQuery("")}>
              Limpiar
            </button>
          )}
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Sucursal</th>
                <th>Estado</th>
                <th>Municipio</th>
                <th>Vigentes</th>
                <th>Por vencer</th>
                <th>Vencidos</th>
                <th>Sin trámite</th>
                <th>Cumplimiento</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr
                  key={s.tramite_id}
                  onClick={() => setSelected(s.tramite_id)}
                  className={selected === s.tramite_id ? "row-selected" : "row-clickable"}
                >
                  <td>{s.tramite_id}</td>
                  <td>{s.nombre}</td>
                  <td>{s.estado || "—"}</td>
                  <td>{s.municipio || "—"}</td>
                  <td><span className="badge status-valid">{s.vigentes}</span></td>
                  <td><span className="badge status-close_to_expiration">{s.por_vencer}</span></td>
                  <td><span className="badge status-expired">{s.vencidos}</span></td>
                  <td>{s.sin_tramite}</td>
                  <td><ComplianceBar value={s.porcentaje} /></td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="td-muted" style={{ textAlign: "center" }}>
                    Sin resultados para "{query}".
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
