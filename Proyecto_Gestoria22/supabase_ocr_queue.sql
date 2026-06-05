-- =============================================================================
-- MIGRACIÓN: Cola de OCR en tiempo real
-- Proyecto: Gestoría Vertiche
-- =============================================================================
--
-- ARQUITECTURA
-- ─────────────────────────────────────────────────────────────────────────────
--
--  [Frontend upload] ──► /api/documents/upload (FastAPI)
--         │
--         ▼
--  [Supabase Storage bucket]
--         │
--         │  (INSERT en storage.objects dispara el trigger)
--         ▼
--  [pending_ocr_queue]  ◄── una fila por archivo subido, estado: pending
--         │
--         │  pg_notify('ocr_queue_new', payload JSON)
--         ▼
--  [ocr_realtime_worker.py]  ──► descarga + OCR ──► upsert en ocr_document_metadata
--         │
--         ▼
--  [pending_ocr_queue]  estado: done / failed
--         │
--         ▼
--  [ocr_document_metadata]  vista materializada refrescada
--         │
--         ▼
--  [Frontend] recibe la actualización vía Supabase Realtime (ocr_document_metadata)
--
-- NOTA SOBRE EL TRIGGER EN storage.objects
-- ─────────────────────────────────────────
-- Supabase no permite crear triggers directamente en storage.objects desde
-- el SQL Editor de usuarios (esquema privado). La solución recomendada —y la
-- que usa este script— es que el endpoint /api/documents/upload inserte la
-- fila en pending_ocr_queue justo después de subir el archivo al bucket.
-- El worker escucha esa tabla con LISTEN/pg_notify Y con polling de respaldo.
--
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 0. Extensiones
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- -----------------------------------------------------------------------------
-- 1. Tabla de cola de OCR pendiente
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pending_ocr_queue (

    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Ruta completa del archivo dentro del bucket (igual que storage_path
    -- en ocr_document_metadata)
    storage_path    TEXT        NOT NULL UNIQUE,
    storage_bucket  TEXT        NOT NULL DEFAULT 'tramites',

    -- Estado del procesamiento
    status          TEXT        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'done', 'failed', 'skipped')),

    -- Número de intentos (para reintentos automáticos)
    attempts        INTEGER     NOT NULL DEFAULT 0,
    max_attempts    INTEGER     NOT NULL DEFAULT 3,

    -- Timestamps de ciclo de vida
    enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    picked_up_at    TIMESTAMPTZ,               -- cuando el worker lo tomó
    finished_at     TIMESTAMPTZ,               -- cuando terminó (bien o mal)

    -- Resultado
    document_id     TEXT,                      -- FK lógica a ocr_document_metadata
    ocr_confidence  NUMERIC(4,3),
    error_message   TEXT,

    -- Contexto extra (carpeta destino, usuario que subió, etc.)
    metadata        JSONB       DEFAULT '{}'
);

COMMENT ON TABLE public.pending_ocr_queue IS
    'Cola FIFO de archivos recién subidos al bucket que esperan OCR. '
    'El worker ocr_realtime_worker.py consume esta tabla en tiempo real.';

CREATE INDEX IF NOT EXISTS idx_queue_status
    ON public.pending_ocr_queue (status, enqueued_at)
    WHERE status IN ('pending', 'failed');

CREATE INDEX IF NOT EXISTS idx_queue_storage_path
    ON public.pending_ocr_queue (storage_path);


-- -----------------------------------------------------------------------------
-- 2. Función que notifica al worker via pg_notify cuando llega un nuevo item
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_notify_ocr_queue()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    payload JSON;
BEGIN
    -- Solo notificamos en INSERT o cuando el status vuelve a 'pending'
    -- (por un reintento manual)
    IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND NEW.status = 'pending') THEN
        payload := json_build_object(
            'id',           NEW.id,
            'storage_path', NEW.storage_path,
            'bucket',       NEW.storage_bucket,
            'enqueued_at',  NEW.enqueued_at
        );
        -- El canal 'ocr_queue_new' es escuchado por el worker con LISTEN
        PERFORM pg_notify('ocr_queue_new', payload::text);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_ocr_queue ON public.pending_ocr_queue;
CREATE TRIGGER trg_notify_ocr_queue
    AFTER INSERT OR UPDATE OF status
    ON public.pending_ocr_queue
    FOR EACH ROW EXECUTE FUNCTION public.fn_notify_ocr_queue();


-- -----------------------------------------------------------------------------
-- 3. Función para encolar un archivo (llamada desde Python con supabase.rpc)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.enqueue_ocr(
    p_storage_path   TEXT,
    p_storage_bucket TEXT DEFAULT 'tramites',
    p_metadata       JSONB DEFAULT '{}'
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO public.pending_ocr_queue (storage_path, storage_bucket, metadata)
    VALUES (p_storage_path, p_storage_bucket, p_metadata)
    ON CONFLICT (storage_path) DO UPDATE
        SET status      = CASE
                            WHEN pending_ocr_queue.status = 'done' THEN 'done'
                            ELSE 'pending'
                          END,
            attempts    = CASE
                            WHEN pending_ocr_queue.status = 'done' THEN pending_ocr_queue.attempts
                            ELSE 0
                          END,
            enqueued_at = NOW(),
            metadata    = p_metadata
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION public.enqueue_ocr IS
    'Encola un archivo para OCR. Si ya existe y está "done", no lo re-procesa. '
    'Llamar desde el endpoint /api/documents/upload justo después del bucket.upload().';


-- -----------------------------------------------------------------------------
-- 4. Función para que el worker "tome" un item de la cola de forma atómica
--    (evita que dos workers procesen el mismo archivo en paralelo)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_ocr_item()
RETURNS SETOF public.pending_ocr_queue
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.pending_ocr_queue
    SET    status      = 'processing',
           picked_up_at = NOW(),
           attempts    = attempts + 1
    WHERE  id = (
        SELECT id
        FROM   public.pending_ocr_queue
        WHERE  status = 'pending'
          AND  attempts < max_attempts
        ORDER  BY enqueued_at ASC
        LIMIT  1
        FOR UPDATE SKIP LOCKED   -- evita bloqueo entre workers concurrentes
    )
    RETURNING *;
END;
$$;


-- -----------------------------------------------------------------------------
-- 5. Función para marcar un item como terminado
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.finish_ocr_item(
    p_id            UUID,
    p_status        TEXT,       -- 'done' | 'failed'
    p_document_id   TEXT        DEFAULT NULL,
    p_confidence    NUMERIC     DEFAULT NULL,
    p_error         TEXT        DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE public.pending_ocr_queue
    SET    status         = p_status,
           finished_at    = NOW(),
           document_id    = COALESCE(p_document_id, document_id),
           ocr_confidence = COALESCE(p_confidence,  ocr_confidence),
           error_message  = p_error
    WHERE  id = p_id;
END;
$$;


-- -----------------------------------------------------------------------------
-- 6. Vista: items pendientes o fallidos recuperables (útil para el frontend)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.ocr_queue_status AS
SELECT
    id,
    storage_path,
    storage_bucket,
    status,
    attempts,
    max_attempts,
    enqueued_at,
    picked_up_at,
    finished_at,
    document_id,
    ocr_confidence,
    error_message,
    -- Tiempo de espera desde que se encoló
    EXTRACT(EPOCH FROM (NOW() - enqueued_at))::INT  AS wait_seconds,
    -- Tiempo de procesamiento si ya terminó
    EXTRACT(EPOCH FROM (finished_at - picked_up_at))::INT AS processing_seconds
FROM public.pending_ocr_queue
ORDER BY enqueued_at DESC;

COMMENT ON VIEW public.ocr_queue_status IS
    'Vista de diagnóstico de la cola. El frontend puede suscribirse a ella '
    'con Supabase Realtime para mostrar el progreso de OCR en tiempo real.';


-- -----------------------------------------------------------------------------
-- 7. RLS y permisos
-- -----------------------------------------------------------------------------
ALTER TABLE public.pending_ocr_queue ENABLE ROW LEVEL SECURITY;

-- El frontend anónimo puede leer la cola (para mostrar progreso)
CREATE POLICY IF NOT EXISTS "anon_read_queue"
    ON public.pending_ocr_queue
    FOR SELECT TO anon USING (true);

-- Solo el backend (service_role) puede insertar/actualizar
-- service_role bypassa RLS automáticamente en Supabase.

GRANT SELECT ON public.pending_ocr_queue  TO anon;
GRANT SELECT ON public.ocr_queue_status   TO anon;
GRANT ALL    ON public.pending_ocr_queue  TO service_role;

GRANT EXECUTE ON FUNCTION public.enqueue_ocr         TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_ocr_item      TO service_role;
GRANT EXECUTE ON FUNCTION public.finish_ocr_item     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_notify_ocr_queue TO service_role;


-- =============================================================================
-- INSTRUCCIONES DE USO
-- =============================================================================
-- 1. Ejecuta este script en el SQL Editor de Supabase (una sola vez,
--    después de haber ejecutado supabase_ocr_metadata.sql).
--
-- 2. En el proyecto Python, reemplaza el endpoint de upload con el que
--    está en upload_endpoint_patch.py — agrega una línea que encola el
--    archivo justo después de bucket.upload().
--
-- 3. Levanta el worker:
--       python ocr_realtime_worker.py
--
-- 4. El frontend puede suscribirse a la tabla pending_ocr_queue o a
--    ocr_document_metadata con Supabase Realtime JS SDK para actualizar
--    el dashboard sin recargar la página:
--
--       const channel = supabase
--         .channel('ocr-updates')
--         .on('postgres_changes', {
--           event: '*', schema: 'public', table: 'ocr_document_metadata'
--         }, (payload) => refetchDashboard())
--         .subscribe()
-- =============================================================================
