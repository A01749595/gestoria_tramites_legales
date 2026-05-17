import { useEffect, useState } from "react";
import { Upload, RefreshCw, FileText } from "lucide-react";
import { getDocuments, uploadDocuments } from "../services/api";

const statusLabel = {
  valid: "Vigente",
  close_to_expiration: "Por vencer",
  expired: "Vencido",
  incomplete: "Sin fecha",
  missing: "Faltante",
  unreadable: "No legible",
};

export default function Documentos() {
  const [files, setFiles] = useState([]);
  const [targetFolder, setTargetFolder] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [data, setData] = useState({ documents: [], bucket_files: [] });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function load() {
    setLoading(true);
    try { setData(await getDocuments()); }
    catch (err) { setMessage(err?.response?.data?.detail || err.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleUpload(e) {
    e.preventDefault();
    if (!files.length) return;
    setLoading(true);
    setMessage("");
    try {
      const res = await uploadDocuments(files, targetFolder, overwrite);
      setMessage(`Carga terminada: ${res.results.filter((r) => r.status === "uploaded").length} archivo(s) subidos.`);
      setFiles([]);
      await load();
    } catch (err) {
      setMessage(err?.response?.data?.detail || err.message || "Error al subir documentos");
    } finally { setLoading(false); }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Documentos</h1>
          <p className="page-sub">Carga PDFs al bucket de Supabase y consulta los estados extraídos.</p>
        </div>
        <button className="btn-secondary" onClick={load}><RefreshCw size={16} /> Actualizar</button>
      </div>

      <form className="card upload-card" onSubmit={handleUpload}>
        <div className="upload-icon"><Upload size={28} /></div>
        <div>
          <h3>Subir documentos PDF</h3>
          <p className="td-muted">Se conserva el bucket de Supabase y el OCR del backend.</p>
        </div>
        <input type="file" multiple accept="application/pdf" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
        <input className="input" placeholder="Carpeta destino opcional" value={targetFolder} onChange={(e) => setTargetFolder(e.target.value)} />
        <label className="checkbox-row"><input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} /> Sobrescribir si existe</label>
        <button className="btn-primary" disabled={!files.length || loading} type="submit"><Upload size={16} /> Subir al bucket</button>
        {message && <p className="td-muted">{message}</p>}
      </form>

      <div className="grid-2">
        <div className="card">
          <div className="section-title-row"><h3>Documentos procesados</h3><span>{data.documents.length}</span></div>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Documento</th><th>Tipo</th><th>Estado</th><th>Vence</th></tr></thead>
              <tbody>
                {data.documents.map((doc) => (
                  <tr key={doc.document_id}>
                    <td>{doc.document_name}</td><td>{doc.document_type}</td>
                    <td><span className={`badge status-${doc.status}`}>{statusLabel[doc.status] || doc.status}</span></td>
                    <td>{doc.expiration_date || "Sin fecha"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <div className="section-title-row"><h3>PDFs en bucket</h3><span>{data.bucket_files.length}</span></div>
          <div className="bucket-list">
            {data.bucket_files.length === 0 ? <p className="td-muted">No hay PDFs listados.</p> : data.bucket_files.map((file) => (
              <div className="bucket-file" key={file}><FileText size={15} /> <span>{file}</span></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
