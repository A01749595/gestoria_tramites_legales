"""
upload_endpoint_patch.py
========================
Parche para el endpoint /api/documents/upload de app.py.

INSTRUCCIONES DE INTEGRACIÓN
──────────────────────────────
Reemplaza la función upload_documents en app.py con la versión de abajo.
El único cambio real respecto al original es la llamada a enqueue_ocr()
después de cada bucket.upload() exitoso.

Diferencias con el original:
  1. Después de bucket.upload() se llama supabase.rpc("enqueue_ocr", ...)
     para insertar la fila en pending_ocr_queue.
  2. La respuesta incluye "queued": true para que el frontend sepa que el
     OCR está en progreso.
  3. BackgroundTasks de FastAPI NO se usan aquí: el OCR corre en el worker
     externo para no bloquear el servidor HTTP ni consumir su memoria.

INTEGRACIÓN CON EL FRONTEND (UploadZone.jsx)
─────────────────────────────────────────────
Después de llamar a uploadDocuments(), el frontend puede suscribirse a
Supabase Realtime para recibir la actualización cuando el OCR termine:

    import { createClient } from '@supabase/supabase-js'

    const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

    // Suscribirse a cambios en ocr_document_metadata
    const channel = sb
      .channel('ocr-live')
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'ocr_document_metadata',
      }, (payload) => {
        // Actualizar el estado del archivo en la UI
        setArchivos(prev => prev.map(a =>
          a.nombre === payload.new.file_name
            ? { ...a, estado: 'valido', ocr: payload.new }
            : a
        ))
      })
      .subscribe()

    // Limpiar al desmontar:
    return () => sb.removeChannel(channel)
"""

# ─── Pegar en app.py: reemplaza la función upload_documents existente ────────

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List

# (El resto de imports ya están en app.py; no duplicar)


@app.post("/api/documents/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    target_folder: str = Form(""),
    overwrite: bool = Form(False),
):
    """
    Sube archivos al bucket de Supabase y los encola para OCR en tiempo real.

    Respuesta por archivo:
      { "file": "ruta/en/bucket.pdf", "status": "uploaded", "bytes": 12345, "queued": true }
    ó
      { "file": "nombre_original.pdf", "status": "failed", "error": "..." }
    """
    global COMPLIANCE_CACHE

    if bucket is None:
        raise HTTPException(
            status_code=400,
            detail=f"Supabase no está conectado: {supabase_error}",
        )

    results = []
    folder  = target_folder.strip().strip("/")

    for uf in files:
        try:
            fname   = safe_filename(uf.filename)
            dest    = f"{folder}/{fname}".strip("/") if folder else fname
            content = await uf.read()

            # ── 1. Subir al bucket (igual que antes) ──────────────────────
            if overwrite:
                try:
                    bucket.remove([dest])
                except Exception:
                    pass

            bucket.upload(
                dest,
                content,
                file_options={"content-type": uf.content_type or "application/pdf"},
            )

            # ── 2. Encolar para OCR en tiempo real ────────────────────────
            # Solo archivos PDF (o que parezcan documentos procesables)
            queued = False
            if fname.lower().endswith(".pdf") or (uf.content_type or "").endswith("pdf"):
                try:
                    supabase.rpc(
                        "enqueue_ocr",
                        {
                            "p_storage_path":   dest,
                            "p_storage_bucket": SUPABASE_BUCKET,
                            "p_metadata": {
                                "original_name": uf.filename,
                                "uploaded_by":   "frontend",
                                "folder":        folder or None,
                            },
                        },
                    ).execute()
                    queued = True
                    logger.info("Encolado para OCR: %s", dest)
                except Exception as eq:
                    # No es crítico: el polling del worker lo recogerá igual
                    logger.warning("enqueue_ocr falló para %r: %s", dest, eq)

            results.append({
                "file":   dest,
                "status": "uploaded",
                "bytes":  len(content),
                "queued": queued,
            })

        except Exception as e:
            results.append({
                "file":   uf.filename,
                "status": "failed",
                "error":  str(e),
            })

    # Invalidar caché de compliance para que el próximo GET /api/dashboard
    # refleje los nuevos documentos (aunque el OCR aún no haya terminado)
    COMPLIANCE_CACHE = None

    return {"results": results}


# ─── Nuevo endpoint: estado de la cola OCR (opcional, para el frontend) ──────

@app.get("/api/ocr/queue")
def get_ocr_queue():
    """
    Devuelve los últimos 50 items de la cola OCR (pendientes, en proceso,
    terminados y fallidos). El frontend puede usarlo para mostrar el
    progreso de cada archivo subido.
    """
    if supabase is None:
        raise HTTPException(status_code=503, detail="Supabase no conectado")
    try:
        resp = (
            supabase.table("pending_ocr_queue")
            .select(
                "id,storage_path,status,attempts,enqueued_at,"
                "picked_up_at,finished_at,ocr_confidence,error_message"
            )
            .order("enqueued_at", desc=True)
            .limit(50)
            .execute()
        )
        return {"queue": resp.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ocr/status/{document_id}")
def get_ocr_status(document_id: str):
    """
    Devuelve el estado del OCR de un documento específico.
    El frontend puede hacer polling de este endpoint cada 2 s
    después de subir un archivo para mostrar un spinner de progreso.
    """
    if supabase is None:
        raise HTTPException(status_code=503, detail="Supabase no conectado")
    try:
        # Buscar en la tabla de metadatos
        meta = (
            supabase.table("ocr_document_metadata")
            .select(
                "document_id,document_name,status,ocr_confidence,"
                "ocr_mode,processing_time,error_message,last_checked_at"
            )
            .eq("document_id", document_id)
            .maybe_single()
            .execute()
        )
        if meta.data:
            return {"ready": True, "data": meta.data}

        # Si no está en metadatos, buscar en la cola
        queue = (
            supabase.table("pending_ocr_queue")
            .select("status,attempts,enqueued_at,error_message")
            .eq("document_id", document_id)
            .maybe_single()
            .execute()
        )
        return {
            "ready": False,
            "queue": queue.data if queue.data else {"status": "not_found"},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
