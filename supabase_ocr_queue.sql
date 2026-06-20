-- =============================================================================
-- MIGRACIÓN: Cola de OCR en tiempo real — pending_ocr_queue
-- Proyecto: Gestoría Vertiche
-- =============================================================================
--
-- REQUISITO PREVIO: supabase_ocr_metadata.sql ya fue ejecutado.
-- Este script SOLO agrega la cola y las funciones del worker en tiempo real.
-- NO toca la tabla ocr_document_metadata existente.
--
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------------------
-- Tabla de cola
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pending_ocr_queue (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    storage_path    TEXT        NOT NULL UNIQUE,
    storage_bucket  TEXT        NOT NULL DEFAULT 'tramites',
    status          TEXT        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','processing','done','failed','skipped')),
    attempts        INTEGER     NOT NULL DEFAULT 0,
    max_attempts    INTEGER     NOT NULL DEFAULT 3,
    enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    picked_up_at    TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    document_id     TEXT,
    ocr_confidence  NUMERIC(4,3),
    error_message   TEXT,
    metadata        JSONB       DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_queue_status
    ON public.pending_ocr_queue (status, enqueued_at)
    WHERE status IN ('pending', 'failed');

CREATE INDEX IF NOT EXISTS idx_queue_storage_path
    ON public.pending_ocr_queue (storage_path);

-- -----------------------------------------------------------------------------
-- Trigger: pg_notify al worker cuando llega un item nuevo
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_notify_ocr_queue()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE payload JSON;
BEGIN
    IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND NEW.status = 'pending') THEN
        payload := json_build_object(
            'id',           NEW.id,
            'storage_path', NEW.storage_path,
            'bucket',       NEW.storage_bucket,
            'enqueued_at',  NEW.enqueued_at
        );
        PERFORM pg_notify('ocr_queue_new', payload::text);
    END IF;
    RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS trg_notify_ocr_queue ON public.pending_ocr_queue;
CREATE TRIGGER trg_notify_ocr_queue
    AFTER INSERT OR UPDATE OF status
    ON public.pending_ocr_queue
    FOR EACH ROW EXECUTE FUNCTION public.fn_notify_ocr_queue();

-- -----------------------------------------------------------------------------
-- Función: encolar un archivo desde el endpoint de upload
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.enqueue_ocr(
    p_storage_path   TEXT,
    p_storage_bucket TEXT DEFAULT 'tramites',
    p_metadata       JSONB DEFAULT '{}'
)
RETURNS UUID LANGUAGE plpgsql AS $$
DECLARE v_id UUID;
BEGIN
    INSERT INTO public.pending_ocr_queue (storage_path, storage_bucket, metadata)
    VALUES (p_storage_path, p_storage_bucket, p_metadata)
    ON CONFLICT (storage_path) DO UPDATE
        SET status      = CASE WHEN pending_ocr_queue.status = 'done' THEN 'done' ELSE 'pending' END,
            attempts    = CASE WHEN pending_ocr_queue.status = 'done' THEN pending_ocr_queue.attempts ELSE 0 END,
            enqueued_at = NOW(),
            metadata    = p_metadata
    RETURNING id INTO v_id;
    RETURN v_id;
END; $$;

-- -----------------------------------------------------------------------------
-- Función: claim atómico (evita procesar el mismo archivo dos veces)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_ocr_item()
RETURNS SETOF public.pending_ocr_queue LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    UPDATE public.pending_ocr_queue
    SET    status       = 'processing',
           picked_up_at = NOW(),
           attempts     = attempts + 1
    WHERE  id = (
        SELECT id FROM public.pending_ocr_queue
        WHERE  status = 'pending' AND attempts < max_attempts
        ORDER  BY enqueued_at ASC LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END; $$;

-- -----------------------------------------------------------------------------
-- Función: marcar item como terminado
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.finish_ocr_item(
    p_id          UUID,
    p_status      TEXT,
    p_document_id TEXT    DEFAULT NULL,
    p_confidence  NUMERIC DEFAULT NULL,
    p_error       TEXT    DEFAULT NULL
)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    UPDATE public.pending_ocr_queue
    SET status         = p_status,
        finished_at    = NOW(),
        document_id    = COALESCE(p_document_id, document_id),
        ocr_confidence = COALESCE(p_confidence, ocr_confidence),
        error_message  = p_error
    WHERE id = p_id;
END; $$;

-- -----------------------------------------------------------------------------
-- Vista de diagnóstico
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.ocr_queue_status AS
SELECT id, storage_path, storage_bucket, status, attempts, max_attempts,
       enqueued_at, picked_up_at, finished_at, document_id, ocr_confidence,
       error_message,
       EXTRACT(EPOCH FROM (NOW() - enqueued_at))::INT       AS wait_seconds,
       EXTRACT(EPOCH FROM (finished_at - picked_up_at))::INT AS processing_seconds
FROM public.pending_ocr_queue
ORDER BY enqueued_at DESC;

-- -----------------------------------------------------------------------------
-- RLS y permisos
-- -----------------------------------------------------------------------------
ALTER TABLE public.pending_ocr_queue ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'pending_ocr_queue'
          AND policyname = 'anon_read_queue'
    ) THEN
        CREATE POLICY anon_read_queue
            ON public.pending_ocr_queue FOR SELECT TO anon USING (true);
    END IF;
END $$;

GRANT SELECT ON public.pending_ocr_queue TO anon;
GRANT SELECT ON public.ocr_queue_status  TO anon;
GRANT ALL    ON public.pending_ocr_queue TO service_role;

GRANT EXECUTE ON FUNCTION public.enqueue_ocr         TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_ocr_item      TO service_role;
GRANT EXECUTE ON FUNCTION public.finish_ocr_item     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_notify_ocr_queue TO service_role;

-- =============================================================================
-- VERIFICACIÓN (ejecuta en SQL Editor para confirmar que todo quedó bien)
-- =============================================================================
-- SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public'
--     AND table_name IN ('pending_ocr_queue','ocr_document_metadata');
--
-- SELECT routine_name FROM information_schema.routines
--   WHERE routine_schema = 'public'
--     AND routine_name IN ('enqueue_ocr','claim_ocr_item','finish_ocr_item',
--                          'refresh_ocr_dashboard_summary');
-- =============================================================================