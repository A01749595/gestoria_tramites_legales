import { useState, useRef } from "react";
import { Upload, FileCheck, X, File } from "lucide-react";

export default function UploadZone({ onUpload }) {
  const [dragging, setDragging] = useState(false);
  const [archivos, setArchivos] = useState([]);
  const inputRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    agregarArchivos(files);
  };

  const agregarArchivos = (files) => {
    const nuevos = files.map((f) => ({
      id: Date.now() + Math.random(),
      nombre: f.name,
      tamano: (f.size / 1024).toFixed(1) + " KB",
      tipo: f.type,
      estado: "pendiente", // pendiente | validando | valido | invalido
    }));
    setArchivos((prev) => [...prev, ...nuevos]);

    // Aquí se conectará con el backend para validar
    // Por ahora simula un proceso de validación
    nuevos.forEach((archivo) => {
      setTimeout(() => {
        setArchivos((prev) =>
          prev.map((a) =>
            a.id === archivo.id
              ? { ...a, estado: "validando" }
              : a
          )
        );
        setTimeout(() => {
          setArchivos((prev) =>
            prev.map((a) =>
              a.id === archivo.id
                ? {
                    ...a,
                    estado: Math.random() > 0.3 ? "valido" : "invalido",
                    mensaje:
                      Math.random() > 0.3
                        ? "Documento válido"
                        : "Fecha de expedición no válida",
                  }
                : a
            )
          );
        }, 1500);
      }, 500);
    });

    if (onUpload) onUpload(nuevos);
  };

  const eliminar = (id) => {
    setArchivos((prev) => prev.filter((a) => a.id !== id));
  };

  const estadoIcon = (estado) => {
    if (estado === "valido") return <FileCheck size={16} className="estado-valido" />;
    if (estado === "invalido") return <X size={16} className="estado-invalido" />;
    return <File size={16} className="estado-pending" />;
  };

  return (
    <div className="upload-container">
      {/* Zona de drop */}
      <div
        className={`upload-zone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          className="upload-input-hidden"
          onChange={(e) => agregarArchivos(Array.from(e.target.files))}
          accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
        />
        <Upload size={36} className="upload-icon" />
        <p className="upload-title">Arrastra documentos aquí</p>
        <p className="upload-sub">o haz clic para seleccionar archivos</p>
        <p className="upload-types">PDF, JPG, PNG, DOC — Máx. 10MB por archivo</p>
      </div>

      {/* Lista de archivos subidos */}
      {archivos.length > 0 && (
        <div className="upload-lista">
          {archivos.map((archivo) => (
            <div key={archivo.id} className={`upload-item upload-${archivo.estado}`}>
              <div className="upload-item-info">
                {estadoIcon(archivo.estado)}
                <div>
                  <p className="upload-nombre">{archivo.nombre}</p>
                  <p className="upload-tamano">
                    {archivo.tamano}
                    {archivo.estado === "validando" && " · Validando..."}
                    {archivo.mensaje && ` · ${archivo.mensaje}`}
                  </p>
                </div>
              </div>
              <button
                className="upload-eliminar"
                onClick={() => eliminar(archivo.id)}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
