import UploadZone from "../components/UploadZone";
import { sucursales } from "../data/mockData";
import { useState } from "react";
import { CheckCircle, XCircle, Clock, FileText } from "lucide-react";

const tiposTramite = [
  "Licencia de Funcionamiento",
  "Registro Sanitario",
  "Permiso de Uso de Suelo",
  "Aviso de Funcionamiento COFEPRIS",
  "Dictamen de Protección Civil",
  "Licencia Ambiental",
  "Registro de Marca",
  "Permiso de Importación",
];

export default function Documentos() {
  const [sucursalId, setSucursalId] = useState("");
  const [tramiteTipo, setTramiteTipo] = useState("");
  const [archivosSubidos, setArchivosSubidos] = useState([]);

  const resumen = {
    validos: archivosSubidos.filter((a) => a.estado === "valido").length,
    invalidos: archivosSubidos.filter((a) => a.estado === "invalido").length,
    validando: archivosSubidos.filter((a) => a.estado === "validando").length,
    pendientes: archivosSubidos.filter((a) => a.estado === "pendiente").length,
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Carga de Documentos</h1>
          <p className="page-sub">
            Sube y valida los documentos para tus trámites
          </p>
        </div>
      </div>

      <div className="docs-grid">
        {/* Panel izquierdo: formulario + uploader */}
        <div className="docs-main">
          <div className="card">
            <h2 className="card-title">Información del Trámite</h2>
            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">Sucursal</label>
                <select
                  className="form-select"
                  value={sucursalId}
                  onChange={(e) => setSucursalId(e.target.value)}
                >
                  <option value="">Selecciona una sucursal...</option>
                  {sucursales.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre} — {s.estado}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Tipo de Trámite</label>
                <select
                  className="form-select"
                  value={tramiteTipo}
                  onChange={(e) => setTramiteTipo(e.target.value)}
                >
                  <option value="">Selecciona el trámite...</option>
                  {tiposTramite.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">Documentos a Cargar</h2>
            <UploadZone
              onUpload={(nuevos) =>
                setArchivosSubidos((prev) => [...prev, ...nuevos])
              }
            />
          </div>

          {archivosSubidos.length > 0 && sucursalId && tramiteTipo && (
            <button className="btn-primary btn-full">
              <FileText size={16} />
              Enviar para Revisión
              {/* Aquí se conectará con el backend */}
            </button>
          )}
        </div>

        {/* Panel derecho: guía + resumen */}
        <div className="docs-side">
          {/* Resumen de validación */}
          {archivosSubidos.length > 0 && (
            <div className="card">
              <h2 className="card-title">Estado de Validación</h2>
              <div className="validacion-resumen">
                <div className="val-item">
                  <CheckCircle size={16} className="icon-green" />
                  <span>{resumen.validos} válidos</span>
                </div>
                <div className="val-item">
                  <XCircle size={16} className="icon-red" />
                  <span>{resumen.invalidos} inválidos</span>
                </div>
                <div className="val-item">
                  <Clock size={16} className="icon-amber" />
                  <span>
                    {resumen.validando + resumen.pendientes} en revisión
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Guía de documentos */}
          <div className="card">
            <h2 className="card-title">Documentos Requeridos</h2>
            <p className="card-sub">
              {tramiteTipo
                ? `Para: ${tramiteTipo}`
                : "Selecciona un trámite para ver qué documentos necesitas."}
            </p>
            {tramiteTipo && (
              <div className="docs-requeridos">
                {/* Aquí el backend retornará la lista real */}
                {[
                  "Acta constitutiva",
                  "Identificación oficial del representante",
                  "Comprobante de domicilio",
                  "Pago de derechos",
                ].map((doc, i) => (
                  <div key={i} className="doc-requerido-item">
                    <FileText size={14} className="icon-muted" />
                    <span>{doc}</span>
                  </div>
                ))}
                <p className="card-sub" style={{ marginTop: "12px" }}>
                  * La lista definitiva se cargará desde el backend según el tipo de trámite.
                </p>
              </div>
            )}
          </div>

          {/* Info del sistema de validación */}
          <div className="card card-info">
            <h3 className="card-title">¿Cómo funciona la validación?</h3>
            <p className="card-sub">
              El sistema revisará automáticamente que cada documento cumpla con:
            </p>
            <ul className="info-lista">
              <li>Fecha de vigencia válida</li>
              <li>Legibilidad del documento</li>
              <li>Coincidencia de datos con el expediente</li>
              <li>Formato aceptado (PDF, JPG, PNG)</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
