import { useEffect, useMemo, useState } from "react";
import {
  ClipboardList,
  RefreshCw,
  Save,
  Plus,
  Trash2,
  Search,
  RotateCcw,
  CheckCircle,
  AlertTriangle,
} from "lucide-react";
import {
  getTramites,
  saveTramiteSucursal,
  deleteTramiteSucursal,
  resetTramites,
} from "../services/api";

// Los 5 trámites requeridos (orden fijo). Si una sucursal nueva se crea
// desde cero, arranca con estos 5 permisos vacíos.
const TRAMITES_BASE = [
  "Aviso de funcionamiento",
  "Uso de suelo",
  "Anuncio",
  "Protección Civil Visto Bueno",
  "Licencia Ambiental",
];

// Sugerencias para el campo de vigencia (datalist). El usuario puede
// escribir una fecha dd/mm/aaaa o elegir uno de estos estados.
const VIGENCIA_SUGERENCIAS = [
  "Permanente",
  "Pagado",
  "Pendiente",
  "Ingreso",
  "Vo Bo",
  "No aplica",
  "Sin trámite",
];

function nuevaSucursalVacia() {
  return {
    tramite_id: "",
    nombre: "",
    estado: "",
    municipio: "",
    permisos: TRAMITES_BASE.map((permiso, i) => ({
      no: String(i + 1),
      permiso,
      vigencia_2025: "",
      vigencia_2026: "",
    })),
    cumplimiento: { porcentaje: 0 },
  };
}

const norm = (s) =>
  (s || "")
    .toString()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

export default function Tramites() {
  const [sucursales, setSucursales] = useState([]);
  const [requeridos, setRequeridos] = useState(TRAMITES_BASE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  // Borrador editable de la sucursal seleccionada.
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await getTramites();
      setSucursales(data.sucursales || []);
      setRequeridos(data.tramites_requeridos || TRAMITES_BASE);
      // Si no hay nada seleccionado, toma la primera.
      if (!selectedId && data.sucursales?.length) {
        selectSucursal(data.sucursales[0], data.sucursales);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No se pudieron cargar los trámites");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectSucursal(s, lista = sucursales) {
    const found = lista.find((x) => x.tramite_id === s.tramite_id) || s;
    setSelectedId(found.tramite_id);
    // Clon profundo para no mutar el estado original mientras se edita.
    setDraft(JSON.parse(JSON.stringify(found)));
    setMessage("");
  }

  function nuevaSucursal() {
    const s = nuevaSucursalVacia();
    setSelectedId("__nueva__");
    setDraft(s);
    setMessage("");
  }

  // --- Edición del borrador ---
  function setField(field, value) {
    setDraft((d) => ({ ...d, [field]: value }));
  }
  function setPermiso(idx, field, value) {
    setDraft((d) => {
      const permisos = d.permisos.map((p, i) =>
        i === idx ? { ...p, [field]: value } : p,
      );
      return { ...d, permisos };
    });
  }
  function addPermiso() {
    setDraft((d) => ({
      ...d,
      permisos: [
        ...d.permisos,
        { no: String(d.permisos.length + 1), permiso: "", vigencia_2025: "", vigencia_2026: "" },
      ],
    }));
  }
  function removePermiso(idx) {
    setDraft((d) => ({
      ...d,
      permisos: d.permisos.filter((_, i) => i !== idx),
    }));
  }

  async function handleSave() {
    if (!draft.tramite_id.trim() || !draft.nombre.trim()) {
      setError("El ID del trámite y el nombre de la sucursal son obligatorios.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const res = await saveTramiteSucursal({
        tramite_id: draft.tramite_id.trim(),
        nombre: draft.nombre.trim(),
        estado: draft.estado || "",
        municipio: draft.municipio || "",
        permisos: draft.permisos.map((p) => ({
          no: p.no || "",
          permiso: p.permiso || "",
          vigencia_2025: p.vigencia_2025 || "",
          vigencia_2026: p.vigencia_2026 || "",
        })),
      });
      setMessage(
        `Sucursal ${res.sucursal.tramite_id} guardada. Cumplimiento: ${res.sucursal.cumplimiento.porcentaje}%`,
      );
      await load();
      setSelectedId(res.sucursal.tramite_id);
      setDraft(JSON.parse(JSON.stringify(res.sucursal)));
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No se pudo guardar la sucursal");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!draft?.tramite_id || selectedId === "__nueva__") return;
    if (!window.confirm(`¿Eliminar la sucursal ${draft.tramite_id}?`)) return;
    try {
      await deleteTramiteSucursal(draft.tramite_id);
      setMessage(`Sucursal ${draft.tramite_id} eliminada.`);
      setSelectedId(null);
      setDraft(null);
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    }
  }

  async function handleReset() {
    if (
      !window.confirm(
        "Esto restaura TODOS los trámites a los datos originales del documento. ¿Continuar?",
      )
    )
      return;
    try {
      const data = await resetTramites();
      setSucursales(data.sucursales || []);
      setMessage("Trámites restaurados a los datos originales.");
      if (data.sucursales?.length) selectSucursal(data.sucursales[0], data.sucursales);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    }
  }

  const q = norm(query.trim());
  const filtered = useMemo(() => {
    if (!q) return sucursales;
    return sucursales.filter((s) =>
      [s.tramite_id, s.nombre, s.estado, s.municipio].some((v) => norm(v).includes(q)),
    );
  }, [sucursales, q]);

  function pct(s) {
    return s.cumplimiento?.porcentaje ?? 0;
  }
  function pctColor(v) {
    return v >= 80 ? "var(--green)" : v >= 50 ? "var(--amber)" : "var(--red)";
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Trámites — llenado manual</h1>
          <p className="page-sub">
            Captura la vigencia de los trámites requeridos por sucursal. Los datos se
            guardan en el servidor y alimentan el tab "Trámites por sucursal" del
            dashboard.
          </p>
        </div>
        <div className="actions-row">
          <button className="btn-secondary" onClick={load} disabled={loading}>
            <RefreshCw size={16} /> Recargar
          </button>
          <button className="btn-secondary" onClick={handleReset}>
            <RotateCcw size={16} /> Restaurar original
          </button>
          <button className="btn-primary" onClick={nuevaSucursal}>
            <Plus size={16} /> Nueva sucursal
          </button>
        </div>
      </div>

      {error && <div className="card card-error">{error}</div>}
      {message && <div className="card card-info">{message}</div>}

      <div className="tramites-layout">
        {/* ─── Lista lateral de sucursales ─── */}
        <div className="card tramites-list">
          <div className="section-title-row">
            <h3>Sucursales</h3>
            <span className="td-muted">{filtered.length}</span>
          </div>
          <div className="table-search">
            <Search size={15} />
            <input
              className="table-search-input"
              placeholder="Buscar sucursal..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && (
              <button className="table-search-clear" onClick={() => setQuery("")}>
                Limpiar
              </button>
            )}
          </div>
          <div className="tramites-list-items">
            {loading && <p className="td-muted">Cargando...</p>}
            {!loading && filtered.length === 0 && (
              <p className="td-muted">Sin sucursales.</p>
            )}
            {filtered.map((s) => {
              const v = pct(s);
              return (
                <button
                  key={s.tramite_id}
                  className={`tramite-item ${selectedId === s.tramite_id ? "active" : ""}`}
                  onClick={() => selectSucursal(s)}
                >
                  <div className="tramite-item-head">
                    <strong>{s.tramite_id}</strong>
                    <span
                      className="tramite-item-pct"
                      style={{ color: pctColor(v) }}
                    >
                      {v}%
                    </span>
                  </div>
                  <span className="tramite-item-name">{s.nombre}</span>
                  <div className="tramite-item-bar">
                    <div
                      className="tramite-item-bar-fill"
                      style={{ width: `${v}%`, background: pctColor(v) }}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ─── Formulario de edición ─── */}
        <div className="card tramites-form">
          {!draft ? (
            <p className="td-muted">
              Selecciona una sucursal de la lista o crea una nueva para empezar a
              capturar.
            </p>
          ) : (
            <>
              <div className="section-title-row">
                <h3>
                  {selectedId === "__nueva__"
                    ? "Nueva sucursal"
                    : `Editar ${draft.tramite_id}`}
                </h3>
                {draft.cumplimiento && (
                  <span
                    className="badge"
                    style={{
                      color: pctColor(draft.cumplimiento.porcentaje),
                      borderColor: pctColor(draft.cumplimiento.porcentaje),
                    }}
                  >
                    {draft.cumplimiento.porcentaje}% cumplimiento
                  </span>
                )}
              </div>

              {/* Datos de la sucursal */}
              <div className="form-grid">
                <label className="form-field">
                  <span>ID del trámite *</span>
                  <input
                    className="input"
                    placeholder="T-001"
                    value={draft.tramite_id}
                    onChange={(e) => setField("tramite_id", e.target.value)}
                    disabled={selectedId !== "__nueva__"}
                  />
                </label>
                <label className="form-field">
                  <span>Nombre de la sucursal *</span>
                  <input
                    className="input"
                    placeholder="San Antonio Abad"
                    value={draft.nombre}
                    onChange={(e) => setField("nombre", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  <span>Estado</span>
                  <input
                    className="input"
                    placeholder="Puebla"
                    value={draft.estado}
                    onChange={(e) => setField("estado", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  <span>Municipio</span>
                  <input
                    className="input"
                    placeholder="Atlixco"
                    value={draft.municipio}
                    onChange={(e) => setField("municipio", e.target.value)}
                  />
                </label>
              </div>

              {/* Permisos */}
              <div className="section-title-row" style={{ marginTop: 18 }}>
                <h3 style={{ fontSize: 15 }}>Permisos / trámites</h3>
                <button className="btn-secondary btn-sm" onClick={addPermiso}>
                  <Plus size={14} /> Agregar permiso
                </button>
              </div>

              <datalist id="vigencia-sugerencias">
                {VIGENCIA_SUGERENCIAS.map((v) => (
                  <option key={v} value={v} />
                ))}
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
                      const esRequerido = requeridos.some(
                        (r) => norm(r) === norm(p.permiso),
                      );
                      return (
                        <tr key={idx}>
                          <td>
                            <input
                              className="input input-cell"
                              value={p.no}
                              onChange={(e) => setPermiso(idx, "no", e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              className="input input-cell"
                              placeholder="Nombre del permiso"
                              value={p.permiso}
                              onChange={(e) => setPermiso(idx, "permiso", e.target.value)}
                            />
                            {esRequerido && (
                              <span className="req-tag" title="Trámite requerido para el cálculo de cumplimiento">
                                requerido
                              </span>
                            )}
                          </td>
                          <td>
                            <input
                              className="input input-cell"
                              list="vigencia-sugerencias"
                              placeholder="dd/mm/aaaa o estado"
                              value={p.vigencia_2025}
                              onChange={(e) =>
                                setPermiso(idx, "vigencia_2025", e.target.value)
                              }
                            />
                          </td>
                          <td>
                            <input
                              className="input input-cell"
                              list="vigencia-sugerencias"
                              placeholder="dd/mm/aaaa o estado"
                              value={p.vigencia_2026}
                              onChange={(e) =>
                                setPermiso(idx, "vigencia_2026", e.target.value)
                              }
                            />
                          </td>
                          <td>
                            <button
                              className="icon-btn-danger"
                              onClick={() => removePermiso(idx)}
                              title="Quitar permiso"
                            >
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
                El % de cumplimiento se calcula sobre la columna <strong>Vigencia 2026</strong>{" "}
                de los {requeridos.length} trámites requeridos. Valores válidos: una fecha
                (dd/mm/aaaa), "Permanente", "Pagado", "Pendiente", "No aplica" o "Sin trámite".
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
    </div>
  );
}
