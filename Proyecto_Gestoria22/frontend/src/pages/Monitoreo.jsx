import { useEffect, useState } from "react";
import { Activity, Bell, Send, RefreshCw, X, Plus, AlertCircle, CheckCircle, Info, AlertTriangle, Mail, Filter, GitBranch, Settings, ChevronDown, ChevronUp, Building2 } from "lucide-react";
import { getMonitoring, sendNotificationTest, sendExpiredAlert, getDashboard, getAlertSegments, sendSegmentedAlert, sendHierarchicalAlerts, listBranches, setBranchEmail, deleteBranchEmail } from "../services/api";

// Regex E.164 (espejo del normalize_phone_e164 en el backend Python).
// "+" + dígito 1-9 + 7 a 14 dígitos = 8-15 dígitos totales.
const E164_RE = /^\+[1-9]\d{7,14}$/;

function cleanPhone(raw) {
  return (raw || "").replace(/[\s\-()]/g, "");
}

function isValidPhone(raw) {
  const c = cleanPhone(raw);
  return E164_RE.test(c);
}

export default function Monitoreo() {
  const [tab, setTab] = useState("notificaciones");
  const [data, setData] = useState(null);
  // Ahora WhatsApp soporta MUCHOS destinatarios: guardamos un array.
  const [recipients, setRecipients] = useState([]);
  const [phoneDraft, setPhoneDraft] = useState("");
  const [phoneError, setPhoneError] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  // ─── Estado para la tarjeta de "Alerta urgente — Documentos vencidos" ───
  const [expiredDocs, setExpiredDocs] = useState([]);
  const [alertEmail, setAlertEmail] = useState("");
  const [alertSending, setAlertSending] = useState(false);
  const [alertResult, setAlertResult] = useState(null);
  const [alertError, setAlertError] = useState("");
  const [alertExpanded, setAlertExpanded] = useState(false);
  const [openBranches, setOpenBranches] = useState({});

  async function load() {
    setError("");
    try {
      setData(await getMonitoring());
      // Traemos también el dashboard para obtener la lista de vencidos
      // y poblar la tarjeta roja de alertas. Si falla no rompe la página.
      try {
        const dash = await getDashboard(false);
        const docs = dash?.data?.documents || [];
        setExpiredDocs(docs.filter((d) => d.status === "expired"));
      } catch {
        // Silencioso: si /api/dashboard aún no está listo, dejamos la
        // lista vacía y se rellena en el próximo refresh.
      }
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function handleSendExpiredAlert(e) {
    e.preventDefault();
    if (!alertEmail.trim()) return;
    setAlertSending(true);
    setAlertError("");
    setAlertResult(null);
    try {
      const res = await sendExpiredAlert(alertEmail.trim());
      setAlertResult(res);
    } catch (err) {
      setAlertError(
        err?.response?.data?.detail ||
          err.message ||
          "Error al enviar la alerta",
      );
    } finally {
      setAlertSending(false);
    }
  }

  function addRecipient() {
    const candidate = cleanPhone(phoneDraft);
    if (!candidate) {
      setPhoneError("Escribe un número primero.");
      return;
    }
    if (!isValidPhone(candidate)) {
      setPhoneError(
        "Formato inválido. Usa E.164: +<código país><número>, ej. +525512345678",
      );
      return;
    }
    if (recipients.includes(candidate)) {
      setPhoneError("Ese número ya está en la lista.");
      return;
    }
    setRecipients([...recipients, candidate]);
    setPhoneDraft("");
    setPhoneError("");
  }

  function removeRecipient(num) {
    setRecipients(recipients.filter((r) => r !== num));
  }

  function handlePhoneKeyDown(e) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addRecipient();
    }
  }

  async function testSend() {
    if (recipients.length === 0) {
      setError("Agrega al menos un destinatario antes de enviar.");
      return;
    }
    setSending(true);
    setError("");
    setResult(null);
    try {
      // El backend ahora acepta array directo en whatsapp_to.
      const res = await sendNotificationTest({ whatsapp_to: recipients });
      setResult(res);
      await load();
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err.message ||
          "No se pudo enviar la prueba",
      );
    } finally {
      setSending(false);
    }
  }

  const logs = data?.logs || {};
  // El nuevo whatsapp_service devuelve { results: [...], summary: {...} }.
  // Soportamos también el formato viejo por si el backend no se actualizó.
  const waResults = result?.whatsapp?.results || [];
  const waSummary = result?.whatsapp?.summary || null;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Alertas</h1>
          <p className="page-sub">
            Prueba el envío a WhatsApp (uno o varios números) y Microsoft Teams con los
            estados y vencimientos de documentos.
          </p>
        </div>
        <button className="btn-secondary" onClick={load}>
          <RefreshCw size={16} /> Actualizar
        </button>
      </div>

      {/* ─── Tab bar ─── */}
      <div className="tab-bar">
        <button className={`tab-btn ${tab === "notificaciones" ? "active" : ""}`} onClick={() => setTab("notificaciones")}>
          <Bell size={15} /> Notificaciones
        </button>
        
        
      </div>

      {error && <div className="card card-error">{error}</div>}

      {/* ════════════════════ TAB: NOTIFICACIONES ════════════════════ */}
      {tab === "notificaciones" && (<>

        {/* 1. Alerta urgente — ancho completo arriba */}
        {(() => {
          const byBranch = {};
          expiredDocs.forEach((d) => {
            const key = d.branch_id || "sin-sucursal";
            if (!byBranch[key]) byBranch[key] = { name: d.branch_name || d.branch_id || "Sin nombre", location: [d.branch_state, d.branch_municipality].filter(Boolean).join(" · "), docs: [] };
            byBranch[key].docs.push(d);
          });
          const branchEntries = Object.entries(byBranch);
          const totalBranches = branchEntries.length;

          return (
            <div className="card card-alert-expired">
              {/* Cabecera — siempre visible, clic despliega */}
              <button
                type="button"
                onClick={() => setAlertExpanded((v) => !v)}
                style={{ width: "100%", background: "none", border: "none", cursor: "pointer", padding: 0, textAlign: "left" }}
              >
                <div className="section-title-row" style={{ pointerEvents: "none" }}>
                  <div className="alert-expired-title">
                    <AlertTriangle size={20} />
                    <h3>Alerta urgente — Documentos vencidos</h3>
                    {expiredDocs.length > 0 && (
                      <span className="alert-expired-count">{expiredDocs.length}</span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="badge badge-urgent">🔴 URGENCIA ALTA</span>
                    {expiredDocs.length > 0 && (
                      <span style={{ color: "#960000", display: "flex", alignItems: "center" }}>
                        {alertExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                      </span>
                    )}
                  </div>
                </div>
                {!alertExpanded && expiredDocs.length > 0 && (
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: "#a00101", pointerEvents: "none" }}>
                    {totalBranches} sucursal{totalBranches !== 1 ? "es" : ""} con {expiredDocs.length} documento{expiredDocs.length !== 1 ? "s" : ""} vencido{expiredDocs.length !== 1 ? "s" : ""} — haz clic para ver el detalle
                  </p>
                )}
              </button>

              {expiredDocs.length === 0 && (
                <p className="td-muted" style={{ marginTop: 8 }}>No hay documentos vencidos registrados.</p>
              )}

              {/* Lista desplegable */}
              {alertExpanded && expiredDocs.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14, marginBottom: 20 }}>
                  {branchEntries.map(([bid, branch]) => {
                    const isOpen = openBranches[bid] !== false;
                    return (
                      <div key={bid} style={{ border: "1px solid #f59090", borderRadius: 8, overflow: "hidden" }}>
                        <button
                          type="button"
                          onClick={() => setOpenBranches((o) => ({ ...o, [bid]: !isOpen }))}
                          style={{ width: "100%", background: "#fee2e2", border: "none", padding: "10px 14px", cursor: "pointer", textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <Building2 size={15} color="#991313" />
                            <strong style={{ fontSize: 13, color: "#7f1d1d" }}>{branch.name}</strong>
                            {branch.location && <span style={{ fontSize: 12, color: "#a91515" }}>· {branch.location}</span>}
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ background: "#a81616", color: "#fff", borderRadius: 12, padding: "1px 9px", fontSize: 11, fontWeight: 700 }}>
                              {branch.docs.length} doc{branch.docs.length !== 1 ? "s" : ""}
                            </span>
                            {isOpen ? <ChevronUp size={15} color="#991414" /> : <ChevronDown size={15} color="#a11313" />}
                          </div>
                        </button>
                        {isOpen && (
                          <table className="data-table" style={{ margin: 0 }}>
                            <thead><tr><th>Documento</th><th>Venció</th><th>Folio</th></tr></thead>
                            <tbody>
                              {branch.docs.map((d) => (
                                <tr key={d.document_id}>
                                  <td>{d.document_name}</td>
                                  <td className="td-expired-date">{d.expiration_date_display || d.expiration_date || "Sin fecha"}</td>
                                  <td>{d.folio_number || "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Formulario de envío — siempre visible */}
              <form onSubmit={handleSendExpiredAlert} className="alert-expired-form" style={{ marginTop: 14 }}>
                <label className="alert-expired-label">
                  <Mail size={14} /> Enviar alerta de urgencia a (uno o varios correos, separados por coma):
                </label>
                <div className="alert-expired-row">
                  <input
                    className="input alert-expired-input"
                    type="text"
                    required
                    placeholder="correo1@ejemplo.com, correo2@ejemplo.com"
                    value={alertEmail}
                    onChange={(e) => setAlertEmail(e.target.value)}
                  />
                  <button className="btn-primary btn-urgent" type="submit" disabled={alertSending || !alertEmail.trim()}>
                    <Send size={15} />
                    {alertSending ? "Enviando..." : "Enviar alerta"}
                  </button>
                </div>
                {alertError && <p className="alert-expired-error">⚠️ {alertError}</p>}
                {alertResult && (
                  <div className="alert-expired-success">
                    <CheckCircle size={18} />
                    <div>
                      <p className="alert-expired-success-title">Alerta enviada correctamente</p>
                      <p className="alert-expired-success-sub">
                        Destinatario(s): <strong>{Array.isArray(alertResult.sent_to) ? alertResult.sent_to.join(", ") : alertResult.sent_to}</strong>{" "}
                        · {alertResult.expired_count} documento{alertResult.expired_count !== 1 ? "s" : ""} incluido{alertResult.expired_count !== 1 ? "s" : ""}
                      </p>
                    </div>
                  </div>
                )}
              </form>
            </div>
          );
        })()}

        {/* 2. Dos columnas */}
        <div className="grid-2">

          {/* Columna izquierda: Correo responsable + Envío jerárquico */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <BranchEmailConfig />
            <HierarchicalAlerts />
          </div>

          {/* Columna derecha: WhatsApp+Teams + Alertas segmentadas */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          
            <SegmentedAlerts />
          </div>

        </div>

      </>)}

      {/* ════════════════════ TAB: DIRECTORIO ════════════════════ */}
      {tab === "directorio" && (
        <div className="card">
          <p className="td-muted" style={{ textAlign: "center", padding: "32px 0" }}>
            El Directorio estará disponible próximamente.
          </p>
        </div>
      )}

      {/* ════════════════════ TAB: OCR ════════════════════ */}
      {tab === "ocr" && (<>
        <div className="card">
          <div className="section-title-row">
            <h3>Estado de servicios</h3>
            <Activity size={18} />
          </div>
          <div className="service-grid">
            {(data?.services || []).map((svc) => (
              <div className="service-row" key={svc.name}>
                <span>{svc.name}</span>
                <span className={`badge ${svc.real ? "badge-real" : "badge-sim"}`}>
                  {svc.real ? "REAL" : "SIMULADO"}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>Historial de extracción OCR / OpenAI</h3>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Archivo</th>
                  <th>Estado</th>
                  <th>Provider</th>
                  <th>Páginas (proc / OCR / digital)</th>
                  <th>Tiempo (s)</th>
                  <th>Confianza</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {(data?.extraction_log || []).map((row, i) => (
                  <tr key={`${row.file}-${i}`}>
                    <td title={row.file}>{row.file}</td>
                    <td>
                      <span className={`badge ${row.status === "ok" ? "badge-real" : "badge-sim"}`}>
                        {row.status}
                      </span>
                    </td>
                    <td>{row.provider || "—"}</td>
                    <td>{row.pages_processed ?? 0} / {row.pages_ocr ?? 0} / {row.pages_digital ?? 0}</td>
                    <td>{row.processing_time != null ? Number(row.processing_time).toFixed(2) : "—"}</td>
                    <td>{row.confidence}</td>
                    <td>{row.error || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </>)}

    </div>
  );
}

function LogCard({ title, rows }) {
  return (
    <div className="card">
      <div className="section-title-row">
        <h3>{title}</h3>
        <span>{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="td-muted">Sin registros.</p>
      ) : (
        <div className="log-list">
          {rows
            .slice(-8)
            .reverse()
            .map((row, i) => (
              <div className="log-item" key={row.message_id || i}>
                <strong>
                  {row.title || row.to || row.message_id || "Mensaje"}
                </strong>
                <span>{row.status || row.mode}</span>
                {row.body && <p>{row.body}</p>}
                {row.text && <p>{row.text}</p>}
                {row.error && <p style={{ color: "var(--red)" }}>{row.error}</p>}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Configuración de correo responsable por sucursal.
// El usuario busca una sucursal con un input y edita su correo.
// ──────────────────────────────────────────────────────────────────
function BranchEmailConfig() {
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);   // branch object
  const [emailDraft, setEmailDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);   // {ok, msg}

  async function load() {
    setLoading(true);
    try {
      const res = await listBranches();
      if (res.pending) { setBranches([]); return; }
      setBranches(res.branches || []);
    } catch {
      setBranches([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function selectBranch(b) {
    setSelected(b);
    setEmailDraft(b.responsible_email || "");
    setFeedback(null);
  }

  async function handleSave() {
    if (!selected) return;
    const email = emailDraft.trim();
    if (!email || !email.includes("@")) {
      setFeedback({ ok: false, msg: "Escribe un correo válido." });
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      await setBranchEmail(selected.branch_id, email);
      setBranches((prev) =>
        prev.map((b) => b.branch_id === selected.branch_id ? { ...b, responsible_email: email } : b)
      );
      setSelected((s) => ({ ...s, responsible_email: email }));
      setFeedback({ ok: true, msg: "Correo guardado correctamente." });
    } catch (err) {
      setFeedback({ ok: false, msg: err?.response?.data?.detail || "Error al guardar." });
    } finally {
      setSaving(false);
    }
  }

  const filtered = branches.filter((b) => {
    const q = search.toLowerCase();
    return (
      (b.branch_name || "").toLowerCase().includes(q) ||
      (b.branch_id || "").toLowerCase().includes(q) ||
      (b.municipality || "").toLowerCase().includes(q)
    );
  });

  
}

// ──────────────────────────────────────────────────────────────────
// Envío jerárquico: escala los correos según días restantes antes
// del vencimiento. El usuario elige sucursal o envía a todas.
// ──────────────────────────────────────────────────────────────────

const TIER_CFG = {
  tier1: {
    label: "40 días por vencer",
    sub: "Solo al responsable de la tienda",
    color: "#1d4ed8",
    bg: "#eff6ff",
    border: "#bfdbfe",
  },
  tier2: {
    label: "20 días por vencer",
    sub: "Supervisor + responsable de la tienda",
    color: "#d97706",
    bg: "#fffbeb",
    border: "#fde68a",
  },
  tier3: {
    label: "Vencido (día 0)",
    sub: "Director + supervisor + responsable de la tienda",
    color: "#dc2626",
    bg: "#fef2f2",
    border: "#fecaca",
  },
};

function HierarchicalAlerts() {
  const [branches, setBranches] = useState([]);
  const [branchId, setBranchId] = useState("");     // "" = todas
  const [branchSearch, setBranchSearch] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listBranches().then((r) => setBranches(r.branches || [])).catch(() => {});
  }, []);

  const selectedBranch = branches.find((b) => b.branch_id === branchId) || null;

  const filteredBranches = branches.filter((b) => {
    const q = branchSearch.toLowerCase();
    return (
      (b.branch_name || "").toLowerCase().includes(q) ||
      (b.branch_id || "").toLowerCase().includes(q)
    );
  });

  async function handleSend(e) {
    e.preventDefault();
    setSending(true);
    setError("");
    setResult(null);
    try {
      const res = await sendHierarchicalAlerts({
        branch_id: branchId || null,
        dry_run: dryRun,
      });
      setResult(res);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "Error al enviar alertas.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="card">
      <div className="section-title-row">
        <div className="alert-expired-title" style={{ color: "var(--text)" }}>
          <GitBranch size={20} />
          <h3 style={{ color: "var(--text)" }}>Envío jerárquico por vencimiento</h3>
        </div>
      </div>

      {/* Tabla de niveles */}
      <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", marginBottom: 20 }}>
        {Object.entries(TIER_CFG).map(([key, t], i, arr) => (
          <div
            key={key}
            style={{
              display: "flex", alignItems: "center", gap: 14,
              padding: "12px 16px",
              background: t.bg,
              borderBottom: i < arr.length - 1 ? `1px solid ${t.border}` : "none",
            }}
          >
            <div style={{ flex: 1 }}>
              <strong style={{ color: t.color, fontSize: 14 }}>{t.label}</strong>
              <p style={{ margin: 0, fontSize: 12, color: "#6b7280", marginTop: 1 }}>{t.sub}</p>
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={handleSend} style={{ display: "flex", flexDirection: "column", gap: 14 }}>

        {/* Selector de sucursal */}
        <div>
          <label style={{ fontSize: 12, color: "#6b7280", display: "block", marginBottom: 4 }}>
            Sucursal (opcional — deja vacío para enviar a todas)
          </label>
          <div style={{ position: "relative" }}>
            <input
              className="input"
              placeholder="— Todas las sucursales —"
              value={selectedBranch ? selectedBranch.branch_name : branchSearch}
              onChange={(e) => {
                setBranchSearch(e.target.value);
                setBranchId("");
                setShowDropdown(true);
              }}
              onFocus={() => setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
            />
            {selectedBranch && (
              <button
                type="button"
                onClick={() => { setBranchId(""); setBranchSearch(""); }}
                style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: 16 }}
              >
                ×
              </button>
            )}
            {showDropdown && branchSearch && !selectedBranch && (
              <div style={{ position: "absolute", zIndex: 10, width: "100%", background: "#fff", border: "1px solid var(--border)", borderRadius: 8, boxShadow: "0 4px 12px rgba(0,0,0,0.1)", maxHeight: 220, overflowY: "auto" }}>
                {filteredBranches.slice(0, 8).map((b) => (
                  <button
                    key={b.branch_id}
                    type="button"
                    onMouseDown={() => { setBranchId(b.branch_id); setBranchSearch(""); setShowDropdown(false); }}
                    style={{ width: "100%", textAlign: "left", background: "none", border: "none", borderBottom: "1px solid #f3f4f6", padding: "9px 14px", cursor: "pointer", display: "flex", justifyContent: "space-between", fontSize: 13 }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "#f9fafb"}
                    onMouseLeave={(e) => e.currentTarget.style.background = "none"}
                  >
                    <span>
                      <strong>{b.branch_name}</strong>
                      <span style={{ color: "#9ca3af", marginLeft: 6, fontSize: 12 }}>{b.branch_id}</span>
                    </span>
                    <span style={{ display: "flex", gap: 4 }}>
                      {b.docs_expired > 0 && <span style={{ background: "#fee2e2", color: "#b91c1c", borderRadius: 4, padding: "1px 6px", fontSize: 11, fontWeight: 600 }}>🚨{b.docs_expired}</span>}
                      {b.docs_expiring > 0 && <span style={{ background: "#fffbeb", color: "#b45309", borderRadius: 4, padding: "1px 6px", fontSize: 11, fontWeight: 600 }}>⚠️{b.docs_expiring}</span>}
                    </span>
                  </button>
                ))}
                {filteredBranches.length === 0 && (
                  <p style={{ margin: 0, padding: "10px 14px", fontSize: 13, color: "#9ca3af" }}>Sin resultados</p>
                )}
              </div>
            )}
          </div>
          {selectedBranch && (
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#6b7280" }}>
              {selectedBranch.branch_id} · {[selectedBranch.state, selectedBranch.municipality].filter(Boolean).join(", ")}
              {selectedBranch.docs_expired > 0 && <span style={{ color: "#b91c1c", marginLeft: 8 }}>🚨 {selectedBranch.docs_expired} vencido{selectedBranch.docs_expired !== 1 ? "s" : ""}</span>}
            </p>
          )}
        </div>

        {/* Toggle previsualización */}
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", fontSize: 14 }}>
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            style={{ width: 16, height: 16 }}
          />
          <span>
            <strong>Solo previsualizar</strong>
            <span style={{ color: "#6b7280", marginLeft: 6, fontSize: 12 }}>— muestra a quién se enviaría sin mandar correos</span>
          </span>
        </label>

        <button className="btn-primary" type="submit" disabled={sending} style={{ alignSelf: "flex-start" }}>
          <Send size={15} />
          {sending
            ? "Procesando..."
            : dryRun
            ? "Previsualizar"
            : branchId
            ? `Enviar alertas a ${selectedBranch?.branch_name || "sucursal"}`
            : "Enviar alertas a todas las sucursales"}
        </button>
      </form>

      {error && <p className="alert-expired-error" style={{ marginTop: 12 }}>⚠️ {error}</p>}

      {/* Resultados */}
      {result && (
        <div style={{ marginTop: 20 }}>
          <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, padding: "10px 18px", textAlign: "center" }}>
              <strong style={{ fontSize: 20, color: "#15803d" }}>{result.branches_processed}</strong>
              <p style={{ margin: "2px 0 0", fontSize: 11, color: "#6b7280" }}>Sucursales</p>
            </div>
            <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: "10px 18px", textAlign: "center" }}>
              <strong style={{ fontSize: 20, color: "#1d4ed8" }}>{result.emails_sent}</strong>
              <p style={{ margin: "2px 0 0", fontSize: 11, color: "#6b7280" }}>Correos {result.dry_run ? "previstos" : "enviados"}</p>
            </div>
            {result.status === "simulated" && (
              <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#92400e", display: "flex", alignItems: "center" }}>
                ⚠️ Modo simulado — configura SMTP en .env para envío real
              </div>
            )}
          </div>

          {(result.results || []).length > 0 && (
            <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
              {(result.results || []).map((branch, bi) => (
                <div key={branch.branch_id} style={{ borderBottom: bi < result.results.length - 1 ? "1px solid var(--border)" : "none", padding: "12px 16px" }}>
                  <strong style={{ fontSize: 13 }}>{branch.branch_name}</strong>
                  <span style={{ color: "#9ca3af", fontSize: 12, marginLeft: 8 }}>{branch.branch_id}</span>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                    {Object.entries(branch.tiers || {}).map(([tierKey, tier]) => {
                      const cfg = TIER_CFG[tierKey];
                      if (!cfg || (tier.skipped && tier.docs === 0)) return null;
                      return (
                        <div key={tierKey} style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 6, padding: "6px 12px", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: cfg.color, fontWeight: 600 }}>{cfg.label}</span>
                          {tier.skipped ? (
                            <span style={{ color: "#9ca3af" }}>— sin destinatarios</span>
                          ) : (
                            <>
                              <span style={{ color: "#374151" }}>· {tier.docs} doc{tier.docs !== 1 ? "s" : ""}</span>
                              <span style={{ color: tier.status === "sent" || tier.status === "dry_run" || tier.status === "simulated" ? "#059669" : "#b41212", fontWeight: 600 }}>
                                [{tier.status}]
                              </span>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Alertas segmentadas: replica la alerta de vencidos pero filtrada por
// sucursal / municipio / estado, con destinatarios designables.
// ──────────────────────────────────────────────────────────────────
function SegmentedAlerts() {
  const [segments, setSegments] = useState(null);
  const [segType, setSegType] = useState("sucursal");
  const [segValue, setSegValue] = useState("");
  const [emails, setEmails] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [sendTeams, setSendTeams] = useState(false);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setSegments(await getAlertSegments());
      } catch {
        // Si falla, los selectores quedan vacíos; no rompe la página.
      }
    })();
  }, []);

  // Lista de opciones según el tipo de segmento elegido.
  const opciones =
    segType === "sucursal"
      ? segments?.sucursales || []
      : segType === "municipio"
      ? segments?.municipios || []
      : segments?.estados || [];

  async function handleSend(e) {
    e.preventDefault();
    if (!segValue) {
      setError("Elige un valor de segmento (sucursal, municipio o estado).");
      return;
    }
    setSending(true);
    setError("");
    setResult(null);
    try {
      const res = await sendSegmentedAlert({
        segment_type: segType,
        segment_value: segValue,
        emails: emails.trim() || null,
        whatsapp: whatsapp.trim() || null,
        send_teams: sendTeams,
      });
      setResult(res);
    } catch (err) {
      setError(
        err?.response?.data?.detail || err.message || "No se pudo enviar la alerta segmentada",
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="card">
      <div className="section-title-row">
        <div className="alert-expired-title" style={{ color: "var(--text)" }}>
          <Filter size={20} />
          <h3 style={{ color: "var(--text)" }}>Alertas segmentadas</h3>
        </div>
        <span className="td-muted">Por sucursal · municipio · estado</span>
      </div>

      <p className="td-muted">
        Manda una alerta de documentos vencidos filtrada por una clasificación. Si no
        escribes destinatarios, se usan los asignados a las sucursales afectadas
        (correo del responsable y del gerente, y su WhatsApp).
      </p>

      <form onSubmit={handleSend} className="segmented-form">
        {/* Tipo de segmento */}
        <div className="segmented-row">
          <label className="form-field">
            <span>Segmentar por</span>
            <select
              className="input"
              value={segType}
              onChange={(e) => {
                setSegType(e.target.value);
                setSegValue("");
              }}
            >
              <option value="sucursal">Sucursal</option>
              <option value="municipio">Municipio</option>
              <option value="estado">Estado</option>
            </select>
          </label>

          <label className="form-field" style={{ flex: 2 }}>
            <span>Valor</span>
            <select
              className="input"
              value={segValue}
              onChange={(e) => setSegValue(e.target.value)}
            >
              <option value="">— Selecciona —</option>
              {opciones.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.value} ({o.expired} vencido{o.expired !== 1 ? "s" : ""} de {o.total})
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Destinatarios */}
        <label className="form-field">
          <span>Correos destino (separados por coma — opcional)</span>
          <input
            className="input"
            placeholder="correo1@ejemplo.com, correo2@ejemplo.com"
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
          />
        </label>

        <label className="form-field">
          <span>WhatsApp destino (E.164, separados por coma — opcional)</span>
          <input
            className="input"
            placeholder="+525512345678, +525587654321"
            value={whatsapp}
            onChange={(e) => setWhatsapp(e.target.value)}
          />
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={sendTeams}
            onChange={(e) => setSendTeams(e.target.checked)}
          />
          <span>Publicar también en el canal de Microsoft Teams</span>
        </label>

        <button className="btn-primary" type="submit" disabled={sending || !segValue}>
          <Send size={16} /> {sending ? "Enviando..." : "Enviar alerta segmentada"}
        </button>
      </form>

      {error && <p className="alert-expired-error">⚠️ {error}</p>}

      {result && (
        <div className="preview-box" style={{ marginTop: 14 }}>
          <strong>Resultado — {result.segment}</strong>
          {result.status === "no_expired" ? (
            <p>{result.message}</p>
          ) : (
            <>
              <p>
                {result.expired_count} documento
                {result.expired_count !== 1 ? "s" : ""} vencido
                {result.expired_count !== 1 ? "s" : ""} en el segmento.
              </p>
              <ul className="segmented-result-list">
                <li>
                  <strong>Email:</strong>{" "}
                  {result.email?.status === "skipped"
                    ? "omitido (sin destinatarios)"
                    : result.email?.status === "simulated"
                    ? "modo simulado"
                    : `${(result.email?.results || []).length} destinatario(s)`}
                </li>
                <li>
                  <strong>WhatsApp:</strong>{" "}
                  {result.whatsapp?.status === "skipped"
                    ? "omitido (sin destinatarios)"
                    : `${result.whatsapp?.summary?.sent ?? 0} enviado(s), ${
                        result.whatsapp?.summary?.failed ?? 0
                      } fallido(s)`}
                </li>
                <li>
                  <strong>Teams:</strong>{" "}
                  {result.teams?.status === "skipped"
                    ? "omitido"
                    : result.teams?.status || "enviado"}
                </li>
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
