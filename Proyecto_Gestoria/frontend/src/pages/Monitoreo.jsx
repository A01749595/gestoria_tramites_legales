import { useEffect, useState } from "react";
import { Activity, Bell, Send, RefreshCw } from "lucide-react";
import { getMonitoring, sendNotificationTest } from "../services/api";

export default function Monitoreo() {
  const [data, setData] = useState(null);
  const [whatsappTo, setWhatsappTo] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try { setData(await getMonitoring()); }
    catch (err) { setError(err?.response?.data?.detail || err.message); }
  }
  useEffect(() => { load(); }, []);

  async function testSend() {
    setSending(true);
    setError("");
    setResult(null);
    try {
      const res = await sendNotificationTest({ whatsapp_to: whatsappTo || undefined });
      setResult(res);
      await load();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No se pudo enviar la prueba");
    } finally { setSending(false); }
  }

  const logs = data?.logs || {};

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Agentes y notificaciones</h1>
          <p className="page-sub">Prueba el envío a WhatsApp y Microsoft Teams con los estados y vencimientos de documentos.</p>
        </div>
        <button className="btn-secondary" onClick={load}><RefreshCw size={16} /> Actualizar</button>
      </div>

      {error && <div className="card card-error">{error}</div>}

      <div className="grid-2">
        <div className="card">
          <div className="section-title-row"><h3>Estado de servicios</h3><Activity size={18} /></div>
          <div className="service-grid">
            {(data?.services || []).map((svc) => (
              <div className="service-row" key={svc.name}>
                <span>{svc.name}</span>
                <span className={`badge ${svc.real ? "badge-real" : "badge-sim"}`}>{svc.real ? "REAL" : "SIMULADO"}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="section-title-row"><h3>Prueba WhatsApp + Teams</h3><Bell size={18} /></div>
          <p className="td-muted">El backend usará credenciales reales si existen en `.env`; si no, quedará en modo simulado.</p>
          <input className="input" placeholder="WhatsApp destino, ej. +525512345678" value={whatsappTo} onChange={(e) => setWhatsappTo(e.target.value)} />
          <button className="btn-primary" onClick={testSend} disabled={sending}>
            <Send size={16} /> {sending ? "Enviando..." : "Enviar prueba"}
          </button>
          {result && (
            <div className="preview-box">
              <strong>Vista previa enviada</strong>
              <pre>{result.preview}</pre>
              <p>Teams: {result.teams?.status}</p>
              <p>WhatsApp: {result.whatsapp?.status}</p>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Agentes inicializados</h3>
        <div className="chip-row">
          {(data?.agents || []).map((agent) => <span className="chip" key={agent}>{agent}</span>)}
        </div>
      </div>

      <div className="grid-2">
        <LogCard title="Mensajes Teams" rows={logs.teams || []} />
        <LogCard title="Mensajes WhatsApp" rows={logs.whatsapp || []} />
      </div>

      <div className="card">
        <h3>Historial de extracción OCR / OpenAI</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Archivo</th><th>Estado</th><th>Provider</th><th>Confianza</th><th>Error</th></tr></thead>
            <tbody>
              {(data?.extraction_log || []).map((row, i) => (
                <tr key={`${row.file}-${i}`}><td>{row.file}</td><td>{row.status}</td><td>{row.provider || "—"}</td><td>{row.confidence}</td><td>{row.error || ""}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function LogCard({ title, rows }) {
  return (
    <div className="card">
      <div className="section-title-row"><h3>{title}</h3><span>{rows.length}</span></div>
      {rows.length === 0 ? <p className="td-muted">Sin registros.</p> : (
        <div className="log-list">
          {rows.slice(-8).reverse().map((row, i) => (
            <div className="log-item" key={row.message_id || i}>
              <strong>{row.title || row.to || row.message_id || "Mensaje"}</strong>
              <span>{row.status || row.mode}</span>
              {row.body && <p>{row.body}</p>}
              {row.text && <p>{row.text}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
