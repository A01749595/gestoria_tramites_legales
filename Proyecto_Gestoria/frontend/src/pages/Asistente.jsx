import { useEffect, useState } from "react";
import { Bot, Send, Plus, Trash2 } from "lucide-react";
import { addPcVisit, chatWithAssistant, getPcVisits } from "../services/api";

const sugerencias = [
  "¿Cuántas alertas críticas hay?",
  "Resumen de notificaciones enviadas",
  "¿Qué documentos vencen este mes?",
  "Visitas de Protección Civil este año",
  "¿Cuál es el score promedio de compliance?",
];

export default function Asistente() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [visits, setVisits] = useState([]);
  const [form, setForm] = useState({ sucursal: "", fecha: new Date().toISOString().slice(0, 10), hora: "", motivo: "" });

  async function loadVisits() {
    const data = await getPcVisits();
    setVisits(data.visits || []);
  }
  useEffect(() => { loadVisits(); }, []);

  async function send(text = input) {
    const content = text.trim();
    if (!content) return;
    const next = [...messages, { role: "user", content }];
    setMessages(next);
    setInput("");
    setThinking(true);
    try {
      const data = await chatWithAssistant(next);
      setMessages([...next, { role: "assistant", content: data.reply }]);
    } catch (err) {
      setMessages([...next, { role: "assistant", content: `No pude responder: ${err.message}` }]);
    } finally { setThinking(false); }
  }

  async function saveVisit(e) {
    e.preventDefault();
    if (!form.sucursal.trim()) return;
    const data = await addPcVisit(form);
    setVisits(data.visits || []);
    setForm({ sucursal: "", fecha: new Date().toISOString().slice(0, 10), hora: "", motivo: "" });
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Verti — Asistente de compliance</h1>
          <p className="page-sub">Chat con OpenAI usando `OPENAI_API_KEY` del `.env` y contexto del workflow.</p>
        </div>
        <button className="btn-secondary" onClick={() => setMessages([])}><Trash2 size={16} /> Limpiar</button>
      </div>

      <div className="grid-2 assistant-layout">
        <div className="card chat-card">
          <div className="section-title-row"><h3>Chat</h3><Bot size={18} /></div>
          <div className="chip-row">
            {sugerencias.map((s) => <button className="chip chip-button" key={s} onClick={() => send(s)}>{s}</button>)}
          </div>
          <div className="chat-window">
            {messages.length === 0 && <div className="empty-chat">Hola, soy Verti. Pregúntame sobre alertas, vencimientos, notificaciones o Protección Civil.</div>}
            {messages.map((msg, i) => <div key={i} className={`chat-bubble ${msg.role}`}>{msg.content}</div>)}
            {thinking && <div className="chat-bubble assistant">Pensando...</div>}
          </div>
          <div className="chat-input-row">
            <input className="input" placeholder="Escríbele a Verti..." value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} />
            <button className="btn-primary" onClick={() => send()} disabled={thinking}><Send size={16} /></button>
          </div>
        </div>

        <div className="card">
          <div className="section-title-row"><h3>Visitas de Protección Civil</h3><Plus size={18} /></div>
          <form className="stack" onSubmit={saveVisit}>
            <input className="input" placeholder="Sucursal visitada" value={form.sucursal} onChange={(e) => setForm({ ...form, sucursal: e.target.value })} />
            <input className="input" type="date" value={form.fecha} onChange={(e) => setForm({ ...form, fecha: e.target.value })} />
            <input className="input" type="time" value={form.hora} onChange={(e) => setForm({ ...form, hora: e.target.value })} />
            <input className="input" placeholder="Motivo u observación" value={form.motivo} onChange={(e) => setForm({ ...form, motivo: e.target.value })} />
            <button className="btn-primary" type="submit">Guardar visita</button>
          </form>
          <div className="visit-list">
            {visits.length === 0 ? <p className="td-muted">Sin visitas registradas.</p> : visits.slice().reverse().map((v) => (
              <div className="visit-item" key={v.id}><strong>{v.sucursal}</strong><span>{v.fecha} {v.hora}</span><p>{v.motivo}</p></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
