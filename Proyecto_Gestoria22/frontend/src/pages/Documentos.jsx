import { useEffect, useMemo, useRef, useState } from "react";
import {
  Upload, RefreshCw, FileText, AlertTriangle, Database, Search,
  ChevronRight, ChevronDown, Eye, CheckCircle, Clock, X,
  ClipboardList, Save, Plus, Trash2, RotateCcw,
} from "lucide-react";
import KpiCard from "../components/KpiCard";
import {
  getDocuments, uploadDocuments, getDashboard,
  getTramites, saveTramiteSucursal, deleteTramiteSucursal, resetTramites,
} from "../services/api";

// ─── Helpers ──────────────────────────────────────────────────────
function number(v) { return Number(v || 0).toLocaleString("es-MX"); }
const norm = (s) => (s || "").toString().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

const STATUS_LABEL = {
  valid: "Vigente", close_to_expiration: "Por vencer", expired: "Vencido",
  incomplete: "Sin fecha", missing: "Faltante", unreadable: "No legible", pending_review: "Pendiente",
};

const TRAMITES_BASE = [
  "Aviso de funcionamiento", "Uso de suelo", "Anuncio",
  "Protección Civil Visto Bueno", "Licencia Ambiental",
];
const VIGENCIA_SUGERENCIAS = ["Permanente","Pagado","Pendiente","Ingreso","Vo Bo","No aplica","Sin trámite"];

// Barra de cumplimiento reutilizable
function ComplianceBar({ value }) {
  const color = value >= 80 ? "#01a085" : value >= 50 ? "#edaa00" : "#9d1333";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 100 }}>
      <div style={{ flex: 1, height: 6, background: "#e5e7eb", borderRadius: 99, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: color, borderRadius: 99 }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 34 }}>{value}%</span>
    </div>
  );
}

// ─── TAB: TRÁMITES ALMACENADOS ────────────────────────────────────
function AlmacenadosTab() {
  const [docs, setDocs]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState(null); // null | 'valid' | 'close_to_expiration' | 'expired'

  // Navegación estratificada: estado > municipio > sucursal > documentos
  const [nivel, setNivel]         = useState(0); // 0=estados,1=municipios,2=sucursales,3=docs
  const [selEstado, setSelEstado]  = useState(null);
  const [selMunicipio, setSelMun]  = useState(null);
  const [selSucursal, setSelSuc]   = useState(null); // { branch_id, branch_name }

  // Modal visor PDF
  const [pdfUrl, setPdfUrl] = useState(null);

  useEffect(() => {
    getDashboard(false)
      .then((res) => setDocs(res.data?.documents || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Docs filtrados por status si hay filtro activo
  const docsFiltrados = useMemo(() => {
    if (!statusFilter) return docs;
    return docs.filter((d) => d.status === statusFilter);
  }, [docs, statusFilter]);

  // Conteos globales para los chips de filtro
  const globalCounts = useMemo(() => ({
    valid:               docs.filter((d) => d.status === "valid").length,
    close_to_expiration: docs.filter((d) => d.status === "close_to_expiration").length,
    expired:             docs.filter((d) => d.status === "expired").length,
  }), [docs]);

  // Agrupar por dimensión
  function groupBy(lista, campo, emptyLabel = "Sin dato") {
    const map = new Map();
    for (const d of lista) {
      const key = d[campo] || emptyLabel;
      if (!map.has(key)) map.set(key, { name: key, total: 0, valid: 0,
        close_to_expiration: 0, expired: 0, incomplete: 0, branchIds: new Set() });
      const row = map.get(key);
      row.total += 1;
      row[d.status] = (row[d.status] || 0) + 1;
      if (d.branch_id) row.branchIds.add(d.branch_id);
    }
    return Array.from(map.values()).map((r) => ({
      ...r,
      sucursales: r.branchIds.size,
      score: r.total > 0
        ? Math.round((100 * (r.valid + 0.5 * r.close_to_expiration)) / r.total)
        : 0,
    })).sort((a, b) => b.total - a.total);
  }

  // ── Vistas por nivel ────────────────────────────────────────────

  // Nivel 0: estados
  const estadosRows = useMemo(
    () => groupBy(docsFiltrados, "branch_state", "Sin estado"),
    [docsFiltrados]
  );

  // Nivel 1: municipios del estado seleccionado
  const municipiosRows = useMemo(() => {
    if (!selEstado) return [];
    return groupBy(
      docsFiltrados.filter((d) => (d.branch_state || "Sin estado") === selEstado),
      "branch_municipality", "Sin municipio"
    );
  }, [docsFiltrados, selEstado]);

  // Nivel 2: sucursales del municipio seleccionado
  const sucursalesRows = useMemo(() => {
    if (!selEstado || !selMunicipio) return [];
    return groupBy(
      docsFiltrados.filter(
        (d) => (d.branch_state || "Sin estado") === selEstado &&
               (d.branch_municipality || "Sin municipio") === selMunicipio
      ),
      "branch_name", "Sin nombre"
    );
  }, [docsFiltrados, selEstado, selMunicipio]);

  // Nivel 3: documentos de la sucursal seleccionada
  const docsSucursal = useMemo(() => {
    if (!selSucursal) return [];
    return docsFiltrados.filter((d) => d.branch_id === selSucursal.branch_id);
  }, [docsFiltrados, selSucursal]);

  function goToEstado(estado) { setSelEstado(estado); setNivel(1); }
  function goToMunicipio(mun)  { setSelMun(mun);      setNivel(2); }
  function goToSucursal(row)   {
    // row viene de sucursalesRows, busco el branch_id real
    const found = docs.find((d) => (d.branch_name || "Sin nombre") === row.name && d.branch_id);
    setSelSuc({ branch_id: found?.branch_id, branch_name: row.name });
    setNivel(3);
  }
  function goNivel(n) {
    setNivel(n);
    if (n < 3) setSelSuc(null);
    if (n < 2) setSelMun(null);
    if (n < 1) setSelEstado(null);
  }

  // Cabeceras de tabla
  const COLS_AGRUPADO = ["Sucursales", "Total", "Vigentes", "Por vencer", "Vencidos", "Sin fecha", "Score"];
  const COLS_SUCURSAL = ["Total", "Vigentes", "Por vencer", "Vencidos", "Sin fecha", "Score"];

  function RowAgrupado({ row, onClick, dimLabel }) {
    return (
      <tr className="row-clickable" onClick={onClick} style={{ cursor: "pointer" }}>
        <td style={{ fontWeight: 600 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {row.name} <ChevronRight size={13} style={{ opacity: 0.5 }} />
          </span>
        </td>
        <td>{row.sucursales}</td>
        <td>{number(row.total)}</td>
        <td><span className="badge status-valid">{row.valid}</span></td>
        <td><span className="badge status-close_to_expiration">{row.close_to_expiration}</span></td>
        <td><span className="badge status-expired">{row.expired}</span></td>
        <td>{row.incomplete}</td>
        <td style={{ minWidth: 120 }}><ComplianceBar value={row.score} /></td>
      </tr>
    );
  }

  function RowSucursalDetalle({ row, onClick }) {
    return (
      <tr className="row-clickable" onClick={onClick} style={{ cursor: "pointer" }}>
        <td style={{ fontWeight: 600 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {row.name} <ChevronRight size={13} style={{ opacity: 0.5 }} />
          </span>
        </td>
        <td>{number(row.total)}</td>
        <td><span className="badge status-valid">{row.valid}</span></td>
        <td><span className="badge status-close_to_expiration">{row.close_to_expiration}</span></td>
        <td><span className="badge status-expired">{row.expired}</span></td>
        <td>{row.incomplete}</td>
        <td style={{ minWidth: 120 }}><ComplianceBar value={row.score} /></td>
      </tr>
    );
  }

  if (loading) return <div className="card">Cargando documentos...</div>;

  return (
    <>
      {/* Chips de cumplimiento / filtro */}
      <div className="card" style={{ padding: "14px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>Estado de cumplimiento</span>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {[
              { key: "valid",               label: "Vigentes",    count: globalCounts.valid,               color: "#01a085", bg: "#e6faf6" },
              { key: "close_to_expiration", label: "Por vencer",  count: globalCounts.close_to_expiration, color: "#edaa00", bg: "#fffbeb" },
              { key: "expired",             label: "Vencidos",    count: globalCounts.expired,             color: "#9d1333", bg: "#fff1f1" },
            ].map(({ key, label, count, color, bg }) => (
              <button
                key={key}
                onClick={() => setStatusFilter(statusFilter === key ? null : key)}
                style={{
                  padding: "7px 16px", borderRadius: 99, fontSize: 13, fontWeight: 600,
                  border: `2px solid ${statusFilter === key ? color : "#e5e7eb"}`,
                  background: statusFilter === key ? bg : "#fff",
                  color: statusFilter === key ? color : "#374151",
                  cursor: "pointer", transition: "all 0.15s",
                }}
              >
                {label}: <strong>{number(count)}</strong>
              </button>
            ))}
            {statusFilter && (
              <button
                onClick={() => setStatusFilter(null)}
                style={{ padding: "7px 12px", borderRadius: 99, fontSize: 12,
                  border: "1px solid #e5e7eb", background: "#f9fafb", color: "#6b7280", cursor: "pointer" }}
              >
                <X size={12} style={{ verticalAlign: -1, marginRight: 3 }} /> Quitar filtro
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, flexWrap: "wrap" }}>
        <button className="btn-link" onClick={() => goNivel(0)}
          style={{ fontWeight: nivel === 0 ? 700 : 400 }}>Estados</button>
        {nivel >= 1 && (
          <>
            <ChevronRight size={13} style={{ color: "#9ca3af" }} />
            <button className="btn-link" onClick={() => goNivel(1)}
              style={{ fontWeight: nivel === 1 ? 700 : 400 }}>{selEstado}</button>
          </>
        )}
        {nivel >= 2 && (
          <>
            <ChevronRight size={13} style={{ color: "#9ca3af" }} />
            <button className="btn-link" onClick={() => goNivel(2)}
              style={{ fontWeight: nivel === 2 ? 700 : 400 }}>{selMunicipio}</button>
          </>
        )}
        {nivel >= 3 && (
          <>
            <ChevronRight size={13} style={{ color: "#9ca3af" }} />
            <span style={{ fontWeight: 700 }}>{selSucursal?.branch_name}</span>
          </>
        )}
      </div>

      {/* Tabla estratificada */}
      <div className="card">
        {/* Nivel 0: Estados */}
        {nivel === 0 && (
          <>
            <div className="section-title-row">
              <h3>Documentos por Estado</h3>
              <span className="td-muted">{estadosRows.length} estados</span>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Estado</th>
                    {COLS_AGRUPADO.map((c) => <th key={c}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {estadosRows.map((row) => (
                    <RowAgrupado key={row.name} row={row} onClick={() => goToEstado(row.name)} />
                  ))}
                  {estadosRows.length === 0 && (
                    <tr><td colSpan={9} className="td-muted">Sin datos.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Nivel 1: Municipios */}
        {nivel === 1 && (
          <>
            <div className="section-title-row">
              <h3>Municipios — {selEstado}</h3>
              <span className="td-muted">{municipiosRows.length} municipios</span>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Municipio</th>
                    {COLS_AGRUPADO.map((c) => <th key={c}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {municipiosRows.map((row) => (
                    <RowAgrupado key={row.name} row={row} onClick={() => goToMunicipio(row.name)} />
                  ))}
                  {municipiosRows.length === 0 && (
                    <tr><td colSpan={9} className="td-muted">Sin datos.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Nivel 2: Sucursales */}
        {nivel === 2 && (
          <>
            <div className="section-title-row">
              <h3>Sucursales — {selMunicipio}</h3>
              <span className="td-muted">{sucursalesRows.length} sucursales</span>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Sucursal</th>
                    {COLS_SUCURSAL.map((c) => <th key={c}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {sucursalesRows.map((row) => (
                    <RowSucursalDetalle key={row.name} row={row} onClick={() => goToSucursal(row)} />
                  ))}
                  {sucursalesRows.length === 0 && (
                    <tr><td colSpan={8} className="td-muted">Sin datos.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Nivel 3: Documentos de la sucursal */}
        {nivel === 3 && (
          <>
            <div className="section-title-row">
              <h3>Documentos — {selSucursal?.branch_name}</h3>
              <span className="td-muted">{docsSucursal.length} documentos</span>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Documento</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Vence</th>
                    <th>Folio</th>
                    <th>Ver</th>
                  </tr>
                </thead>
                <tbody>
                  {docsSucursal.map((doc) => (
                    <tr key={doc.document_id}>
                      <td title={doc.file_url} style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {doc.document_name}
                      </td>
                      <td>{doc.document_type_label || doc.document_type || "—"}</td>
                      <td>
                        <span className={`badge status-${doc.status}`}>
                          {doc.status_label || STATUS_LABEL[doc.status] || doc.status}
                        </span>
                      </td>
                      <td>{doc.expiration_date_display || doc.expiration_date || "Sin fecha"}</td>
                      <td>{doc.folio_number || "—"}</td>
                      <td>
                        {doc.file_url ? (
                          <button
                            className="btn-secondary"
                            style={{ padding: "4px 10px", fontSize: 12 }}
                            onClick={() => setPdfUrl(doc.file_url)}
                          >
                            <Eye size={13} style={{ verticalAlign: -2 }} /> Ver PDF
                          </button>
                        ) : (
                          <span className="td-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {docsSucursal.length === 0 && (
                    <tr><td colSpan={6} className="td-muted">Sin documentos.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* Modal visor PDF */}
      {pdfUrl && (
        <div
          onClick={() => setPdfUrl(null)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
            zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#fff", borderRadius: 12, width: "90vw", height: "90vh",
              display: "flex", flexDirection: "column", overflow: "hidden",
            }}
          >
            <div style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "10px 16px", borderBottom: "1px solid #e5e7eb",
            }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
                Visor de documento
              </span>
              <button
                onClick={() => setPdfUrl(null)}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#6b7280" }}
              >
                <X size={20} />
              </button>
            </div>
            {pdfUrl.startsWith("http") ? (
              <iframe
                src={pdfUrl}
                style={{ flex: 1, border: "none" }}
                title="Visor PDF"
              />
            ) : (
              <div style={{ flex: 1, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 12, padding: 24 }}>
                <FileText size={48} style={{ color: "#9ca3af" }} />
                <p style={{ fontWeight: 600, color: "#374151" }}>Ruta del archivo en Supabase:</p>
                <code style={{ background: "#f3f4f6", padding: "6px 12px", borderRadius: 6,
                  fontSize: 12, wordBreak: "break-all", maxWidth: 600 }}>
                  {pdfUrl}
                </code>
                <p className="td-muted" style={{ fontSize: 12, textAlign: "center" }}>
                  Para ver el PDF directamente, el backend necesita un endpoint de URL firmada de Supabase.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ─── TAB: EDITAR TRÁMITES ─────────────────────────────────────────
function EditarTramitesTab() {
  const [sucursales, setSucursales] = useState([]);
  const [requeridos, setRequeridos] = useState(TRAMITES_BASE);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState("");
  const [message, setMessage]       = useState("");
  const [query, setQuery]           = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft]           = useState(null);
  const [saving, setSaving]         = useState(false);

  function nuevaSucursalVacia() {
    return {
      tramite_id: "", nombre: "", estado: "", municipio: "",
      permisos: TRAMITES_BASE.map((permiso, i) => ({
        no: String(i + 1), permiso, vigencia_2025: "", vigencia_2026: "",
      })),
      cumplimiento: { porcentaje: 0 },
    };
  }

  async function load() {
    setLoading(true); setError("");
    try {
      const data = await getTramites();
      setSucursales(data.sucursales || []);
      setRequeridos(data.tramites_requeridos || TRAMITES_BASE);
      if (!selectedId && data.sucursales?.length) selectSucursal(data.sucursales[0], data.sucursales);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "Error al cargar trámites");
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  function selectSucursal(s, lista = sucursales) {
    const found = lista.find((x) => x.tramite_id === s.tramite_id) || s;
    setSelectedId(found.tramite_id);
    setDraft(JSON.parse(JSON.stringify(found)));
    setMessage("");
  }

  function nuevaSucursal() { setSelectedId("__nueva__"); setDraft(nuevaSucursalVacia()); setMessage(""); }
  function setField(field, value) { setDraft((d) => ({ ...d, [field]: value })); }
  function setPermiso(idx, field, value) {
    setDraft((d) => ({ ...d, permisos: d.permisos.map((p, i) => i === idx ? { ...p, [field]: value } : p) }));
  }
  function addPermiso() {
    setDraft((d) => ({ ...d, permisos: [...d.permisos, { no: String(d.permisos.length + 1), permiso: "", vigencia_2025: "", vigencia_2026: "" }] }));
  }
  function removePermiso(idx) {
    setDraft((d) => ({ ...d, permisos: d.permisos.filter((_, i) => i !== idx) }));
  }

  async function handleSave() {
    if (!draft.tramite_id.trim() || !draft.nombre.trim()) {
      setError("El ID y el nombre de la sucursal son obligatorios."); return;
    }
    setSaving(true); setError(""); setMessage("");
    try {
      const res = await saveTramiteSucursal({
        tramite_id: draft.tramite_id.trim(), nombre: draft.nombre.trim(),
        estado: draft.estado || "", municipio: draft.municipio || "",
        permisos: draft.permisos.map((p) => ({
          no: p.no || "", permiso: p.permiso || "",
          vigencia_2025: p.vigencia_2025 || "", vigencia_2026: p.vigencia_2026 || "",
        })),
      });
      setMessage(`Sucursal ${res.sucursal.tramite_id} guardada. Cumplimiento: ${res.sucursal.cumplimiento.porcentaje}%`);
      await load();
      setSelectedId(res.sucursal.tramite_id);
      setDraft(JSON.parse(JSON.stringify(res.sucursal)));
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "Error al guardar");
    } finally { setSaving(false); }
  }

  async function handleDelete() {
    if (!draft?.tramite_id || selectedId === "__nueva__") return;
    if (!window.confirm(`¿Eliminar la sucursal ${draft.tramite_id}?`)) return;
    try {
      await deleteTramiteSucursal(draft.tramite_id);
      setMessage(`Sucursal ${draft.tramite_id} eliminada.`);
      setSelectedId(null); setDraft(null); await load();
    } catch (err) { setError(err?.response?.data?.detail || err.message); }
  }

  async function handleReset() {
    if (!window.confirm("¿Restaurar TODOS los trámites a los datos originales?")) return;
    try {
      const data = await resetTramites();
      setSucursales(data.sucursales || []);
      setMessage("Trámites restaurados.");
      if (data.sucursales?.length) selectSucursal(data.sucursales[0], data.sucursales);
    } catch (err) { setError(err?.response?.data?.detail || err.message); }
  }

  const q = norm(query.trim());
  const filtered = useMemo(() => {
    if (!q) return sucursales;
    return sucursales.filter((s) => [s.tramite_id, s.nombre, s.estado, s.municipio].some((v) => norm(v).includes(q)));
  }, [sucursales, q]);

  function pct(s) { return s.cumplimiento?.porcentaje ?? 0; }
  function pctColor(v) { return v >= 80 ? "#01a085" : v >= 50 ? "#edaa00" : "#9d1333"; }

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginBottom: 4 }}>
        <button className="btn-secondary" onClick={load} disabled={loading}>
          <RefreshCw size={14} /> Recargar
        </button>
        <button className="btn-secondary" onClick={handleReset}>
          <RotateCcw size={14} /> Restaurar original
        </button>
        <button className="btn-primary" onClick={nuevaSucursal}>
          <Plus size={14} /> Nueva sucursal
        </button>
      </div>

      {error   && <div className="card card-error">{error}</div>}
      {message && <div className="card card-info">{message}</div>}

      <div className="tramites-layout">
        {/* Lista lateral */}
        <div className="card tramites-list">
          <div className="section-title-row">
            <h3>Sucursales</h3>
            <span className="td-muted">{filtered.length}</span>
          </div>
          <div className="table-search">
            <Search size={15} />
            <input className="table-search-input" placeholder="Buscar sucursal..." value={query}
              onChange={(e) => setQuery(e.target.value)} />
            {query && <button className="table-search-clear" onClick={() => setQuery("")}>Limpiar</button>}
          </div>
          <div className="tramites-list-items">
            {loading && <p className="td-muted">Cargando...</p>}
            {!loading && filtered.length === 0 && <p className="td-muted">Sin sucursales.</p>}
            {filtered.map((s) => {
              const v = pct(s);
              return (
                <button key={s.tramite_id}
                  className={`tramite-item ${selectedId === s.tramite_id ? "active" : ""}`}
                  onClick={() => selectSucursal(s)}>
                  <div className="tramite-item-head">
                    <strong>{s.tramite_id}</strong>
                    <span className="tramite-item-pct" style={{ color: pctColor(v) }}>{v}%</span>
                  </div>
                  <span className="tramite-item-name">{s.nombre}</span>
                  <div className="tramite-item-bar">
                    <div className="tramite-item-bar-fill" style={{ width: `${v}%`, background: pctColor(v) }} />
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Formulario de edición */}
        <div className="card tramites-form">
          {!draft ? (
            <p className="td-muted">Selecciona una sucursal o crea una nueva.</p>
          ) : (
            <>
              <div className="section-title-row">
                <h3>{selectedId === "__nueva__" ? "Nueva sucursal" : `Editar ${draft.tramite_id}`}</h3>
                {draft.cumplimiento && (
                  <span className="badge" style={{ color: pctColor(draft.cumplimiento.porcentaje), borderColor: pctColor(draft.cumplimiento.porcentaje) }}>
                    {draft.cumplimiento.porcentaje}% cumplimiento
                  </span>
                )}
              </div>
              <div className="form-grid">
                {[
                  ["ID del trámite *", "tramite_id", "T-001", selectedId !== "__nueva__"],
                  ["Nombre de la sucursal *", "nombre", "San Antonio Abad", false],
                  ["Estado", "estado", "Puebla", false],
                  ["Municipio", "municipio", "Atlixco", false],
                ].map(([label, field, placeholder, disabled]) => (
                  <label className="form-field" key={field}>
                    <span>{label}</span>
                    <input className="input" placeholder={placeholder} value={draft[field]}
                      onChange={(e) => setField(field, e.target.value)} disabled={disabled} />
                  </label>
                ))}
              </div>

              <div className="section-title-row" style={{ marginTop: 18 }}>
                <h3 style={{ fontSize: 15 }}>Permisos / trámites</h3>
                <button className="btn-secondary btn-sm" onClick={addPermiso}>
                  <Plus size={14} /> Agregar permiso
                </button>
              </div>

              <datalist id="vigencia-sugerencias">
                {VIGENCIA_SUGERENCIAS.map((v) => <option key={v} value={v} />)}
              </datalist>

              <div className="table-wrap">
                <table className="data-table tramites-table">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}>No.</th>
                      <th>Permiso</th>
                      <th style={{ width: 150 }}>Vigencia 2025</th>
                      <th style={{ width: 150 }}>Vigencia 2026</th>
                      <th style={{ width: 44 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {draft.permisos.map((p, idx) => {
                      const esRequerido = requeridos.some((r) => norm(r) === norm(p.permiso));
                      return (
                        <tr key={idx}>
                          <td><input className="input input-cell" value={p.no} onChange={(e) => setPermiso(idx, "no", e.target.value)} /></td>
                          <td>
                            <input className="input input-cell" placeholder="Nombre del permiso" value={p.permiso}
                              onChange={(e) => setPermiso(idx, "permiso", e.target.value)} />
                            {esRequerido && <span className="req-tag" title="Requerido">requerido</span>}
                          </td>
                          <td><input className="input input-cell" list="vigencia-sugerencias" placeholder="dd/mm/aaaa o estado"
                            value={p.vigencia_2025} onChange={(e) => setPermiso(idx, "vigencia_2025", e.target.value)} /></td>
                          <td><input className="input input-cell" list="vigencia-sugerencias" placeholder="dd/mm/aaaa o estado"
                            value={p.vigencia_2026} onChange={(e) => setPermiso(idx, "vigencia_2026", e.target.value)} /></td>
                          <td>
                            <button className="icon-btn-danger" onClick={() => removePermiso(idx)} title="Quitar">
                              <Trash2 size={14} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <p className="td-muted" style={{ fontSize: 12, marginTop: 8 }}>
                El % de cumplimiento se calcula sobre <strong>Vigencia 2026</strong> de los {requeridos.length} trámites requeridos.
              </p>

              <div className="actions-row" style={{ marginTop: 14 }}>
                <button className="btn-primary" onClick={handleSave} disabled={saving}>
                  <Save size={16} /> {saving ? "Guardando..." : "Guardar sucursal"}
                </button>
                {selectedId !== "__nueva__" && (
                  <button className="btn-danger" onClick={handleDelete}>
                    <Trash2 size={16} /> Eliminar
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

// ─── TAB: CARGAR DOCUMENTOS ───────────────────────────────────────
const emptyTotals = {
  bucket_total: 0, processed_total: 0, pending_total: 0,
  failed_ocr: 0, failed_llm: 0,
  by_provider: { tesseract: 0, pymupdf: 0, hybrid: 0 },
  by_status: {}, by_type: {},
};

function CargarDocumentosTab() {
  const [files, setFiles]             = useState([]);
  const [targetFolder, setTargetFolder] = useState("");
  const [overwrite, setOverwrite]     = useState(false);
  const [data, setData]               = useState({ documents: [], bucket_files: [],
    totals: emptyTotals, supabase: { connected: false, bucket: "", error: null },
    pending: false, ingest: null });
  const [loading, setLoading]         = useState(false);
  const [message, setMessage]         = useState("");
  const [progress, setProgress]       = useState(null); // null | 0-100
  const abortRef = useRef(null);

  async function load() {
    setLoading(true);
    try {
      const res = await getDocuments();
      setData({
        documents:    res.documents    || [],
        bucket_files: res.bucket_files || [],
        totals:       { ...emptyTotals, ...(res.totals || {}) },
        supabase:     res.supabase     || { connected: false, bucket: "", error: null },
        pending:      !!res.pending,
        ingest:       res.ingest       || null,
      });
    } catch (err) {
      setMessage(err?.response?.data?.detail || err.message);
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleUpload(e) {
    e.preventDefault();
    if (!files.length) return;
    setLoading(true);
    setMessage("");
    setProgress(0);

    // Usamos XMLHttpRequest para tener progreso real
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append("files", file));
    formData.append("target_folder", targetFolder);
    formData.append("overwrite", overwrite ? "true" : "false");

    const xhr = new XMLHttpRequest();
    abortRef.current = xhr;

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) setProgress(Math.round((ev.loaded / ev.total) * 100));
    };

    xhr.onload = async () => {
      setProgress(100);
      try {
        const res = JSON.parse(xhr.responseText);
        const ok = (res.results || []).filter((r) => r.status === "uploaded").length;
        setMessage(`Carga terminada: ${ok} archivo(s) subidos al bucket.`);
        setFiles([]);
      } catch {
        setMessage("Carga completada.");
      }
      await load();
      setLoading(false);
      setTimeout(() => setProgress(null), 2000);
    };

    xhr.onerror = () => {
      setMessage("Error al subir documentos.");
      setProgress(null);
      setLoading(false);
    };

    const { API_BASE } = await import("../services/api");
    xhr.open("POST", `${API_BASE}/api/documents/upload`);
    xhr.send(formData);
  }

  const totals  = data.totals  || emptyTotals;
  const supabase = data.supabase || {};
  const ingest  = data.ingest  || {};
  const ocrTotal = (totals.by_provider?.tesseract || 0) +
    (totals.by_provider?.hybrid || 0) + (totals.by_provider?.pymupdf || 0);
  const ingestBusy = ingest?.phase && ["connecting","listing","ocr"].includes(ingest.phase);

  const kpis = [
    { titulo: "PDFs en bucket",  valor: number(totals.bucket_total),                    icono: "FileText",      color: "blue",  cambio: 0 },
    { titulo: "Procesados",      valor: number(totals.processed_total),                  icono: "CheckCircle",   color: "green", cambio: 0 },
    { titulo: "Pendientes",      valor: number(totals.pending_total),                    icono: "Clock",         color: "amber", cambio: 0 },
    { titulo: "Fallidos",        valor: number(totals.failed_ocr + totals.failed_llm),  icono: "AlertTriangle", color: "red",   cambio: 0 },
    { titulo: "Stack OCR",       valor: number(ocrTotal),                                icono: "FileText",      color: "teal",  cambio: 0 },
  ];

  return (
    <>
      {/* Banner Supabase */}
      <div className={`card ${supabase.connected ? "card-info" : "card-error"}`}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Database size={18} />
          {supabase.connected ? (
            <>
              <strong>Supabase conectado</strong>
              <span className="td-muted">Bucket: <code>{supabase.bucket || "—"}</code></span>
              <span className="badge badge-real">REAL</span>
            </>
          ) : (
            <>
              <strong>Supabase NO conectado</strong>
              <span className="td-muted">{supabase.error || "Configura SUPABASE_URL y SUPABASE_KEY en .env"}</span>
              <span className="badge badge-sim">SIMULADO</span>
            </>
          )}
        </div>
      </div>

      {/* Banner ingesta */}
      {ingestBusy && (
        <div className="card card-info">
          <strong>Procesando documentos...</strong> {ingest.message}
          {ingest.total > 0 && (
            <> ({ingest.processed} / {ingest.total} — {Math.round((100 * (ingest.processed || 0)) / Math.max(1, ingest.total))}%)</>
          )}
        </div>
      )}

      {/* KPIs */}
      <div className="kpi-grid">
        {kpis.map((kpi) => <KpiCard key={kpi.titulo} {...kpi} />)}
      </div>

      {/* Estado de cumplimiento por status */}
      {Object.keys(totals.by_status || {}).length > 0 && (
        <div className="card">
          <div className="section-title-row">
            <h3>Desglose por estado de cumplimiento</h3>
            <span className="td-muted">{totals.processed_total} documentos</span>
          </div>
          <div className="chip-row">
            {Object.entries(totals.by_status || {}).map(([key, n]) => (
              <span className={`badge status-${key}`} key={key}>
                {STATUS_LABEL[key] || key}: <strong style={{ marginLeft: 4 }}>{n}</strong>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Formulario de carga */}
      <form className="card upload-card" onSubmit={handleUpload}>
        <div className="upload-icon"><Upload size={28} /></div>
        <div>
          <h3>Subir documentos PDF</h3>
          <p className="td-muted">
            Los archivos se guardan en el bucket de Supabase y se procesan en la siguiente actualización del dashboard.
          </p>
        </div>

        <input type="file" multiple accept="application/pdf"
          onChange={(e) => setFiles(Array.from(e.target.files || []))} />

        <input className="input" placeholder="Carpeta destino (opcional)"
          value={targetFolder} onChange={(e) => setTargetFolder(e.target.value)} />

        <label className="checkbox-row">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          Sobrescribir si existe
        </label>

        <button className="btn-primary" disabled={!files.length || loading || !supabase.connected} type="submit">
          <Upload size={16} /> Subir al bucket
        </button>

        {/* Progress bar */}
        {progress !== null && (
          <div style={{ marginTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
              <span>{progress < 100 ? "Subiendo archivos..." : "¡Carga completada!"}</span>
              <span>{progress}%</span>
            </div>
            <div style={{ height: 8, background: "#e5e7eb", borderRadius: 99, overflow: "hidden" }}>
              <div style={{
                height: "100%", borderRadius: 99,
                background: progress === 100 ? "#01a085" : "#0e5ed5",
                width: `${progress}%`,
                transition: "width 0.3s ease",
              }} />
            </div>
          </div>
        )}

        {!supabase.connected && (
          <p className="td-muted">
            <AlertTriangle size={14} style={{ display: "inline", verticalAlign: -2, marginRight: 4 }} />
            No se puede subir hasta que Supabase esté conectado.
          </p>
        )}
        {message && <p className="td-muted">{message}</p>}
      </form>
    </>
  );
}

// ─── COMPONENTE PRINCIPAL ─────────────────────────────────────────
const TABS = [
  { key: "almacenados", label: "Trámites Almacenados", icon: FileText },
  { key: "editar",      label: "Editar Trámites",      icon: ClipboardList },
  { key: "cargar",      label: "Cargar Documentos",    icon: Upload },
];

export default function Documentos() {
  const [tab, setTab] = useState("almacenados");

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Documentos</h1>
          <p className="page-sub">Gestión, edición y carga de documentos por sucursal.</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            className={`tab-btn ${tab === key ? "active" : ""}`}
            onClick={() => setTab(key)}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {/* Contenido del tab */}
      {tab === "almacenados" && <AlmacenadosTab />}
      {tab === "editar"      && <EditarTramitesTab />}
      {tab === "cargar"      && <CargarDocumentosTab />}
    </div>
  );
}
