import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({ baseURL: API_BASE, timeout: 120000 });

export async function getHealth() {
  const { data } = await api.get("/api/health");
  return data;
}

export async function getStatus() {
  const { data } = await api.get("/api/status");
  return data;
}

export async function getDashboard(refresh = false) {
  const { data } = await api.get("/api/dashboard", { params: { refresh } });
  return data;
}

export async function getDocuments() {
  const { data } = await api.get("/api/documents");
  return data;
}

export async function uploadDocuments(files, targetFolder = "", overwrite = false) {
  const form = new FormData();
  Array.from(files).forEach((file) => form.append("files", file));
  form.append("target_folder", targetFolder);
  form.append("overwrite", overwrite ? "true" : "false");
  const { data } = await api.post("/api/documents/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getMonitoring() {
  const { data } = await api.get("/api/monitoring");
  return data;
}

export async function sendNotificationTest(payload) {
  const { data } = await api.post("/api/agents/test-notifications", payload);
  return data;
}

export async function getPcVisits() {
  const { data } = await api.get("/api/pc-visits");
  return data;
}

export async function addPcVisit(payload) {
  const { data } = await api.post("/api/pc-visits", payload);
  return data;
}

export async function chatWithAssistant(messages) {
  const { data } = await api.post("/api/assistant/chat", { messages });
  return data;
}

/**
 * Envía el correo HTML de URGENCIA ALTA con la lista de documentos vencidos.
 * @param {string} recipientEmail - uno o varios correos separados por coma.
 * @param {string[] | null} documentIds - lista de document_id a incluir, o
 *        null para mandar TODOS los vencidos.
 */
export async function sendExpiredAlert(recipientEmail, documentIds = null) {
  const { data } = await api.post("/api/agents/send-expired-alert", {
    recipient_email: recipientEmail,
    document_ids: documentIds,
  });
  return data;
}

// ─── Trámites por sucursal (tab de llenado manual) ───

export async function getTramites() {
  const { data } = await api.get("/api/tramites");
  return data;
}

export async function getTramitesResumen() {
  const { data } = await api.get("/api/tramites/resumen");
  return data;
}

export async function saveTramiteSucursal(sucursal) {
  const { data } = await api.post("/api/tramites/sucursal", sucursal);
  return data;
}

export async function deleteTramiteSucursal(tramiteId) {
  const { data } = await api.delete(`/api/tramites/sucursal/${encodeURIComponent(tramiteId)}`);
  return data;
}

export async function resetTramites() {
  const { data } = await api.post("/api/tramites/reset");
  return data;
}

// ─── Alertas segmentadas (sucursal / municipio / estado) ───

export async function getAlertSegments() {
  const { data } = await api.get("/api/agents/segments");
  return data;
}

/**
 * Envía una alerta de vencidos filtrada por segmento.
 * @param {object} payload
 *   - segment_type: "sucursal" | "municipio" | "estado"
 *   - segment_value: string
 *   - emails:   correos separados por coma (opcional)
 *   - whatsapp: números separados por coma (opcional)
 *   - send_teams: boolean
 */
export async function sendSegmentedAlert(payload) {
  const { data } = await api.post("/api/agents/send-segmented-alert", payload);
  return data;
}

// ─── Configuración de correos por sucursal ───

export async function listBranches() {
  const { data } = await api.get("/api/branches");
  return data;
}

export async function setBranchEmail(branchId, responsibleEmail) {
  const { data } = await api.post(`/api/branches/${encodeURIComponent(branchId)}/config`, {
    responsible_email: responsibleEmail,
  });
  return data;
}

export async function deleteBranchEmail(branchId) {
  const { data } = await api.delete(`/api/branches/${encodeURIComponent(branchId)}/config`);
  return data;
}

/**
 * Envía correos jerárquicos por vencimiento de documentos.
 * Escalamiento por días restantes antes del vencimiento:
 *   • 20 < días ≤ 40 → responsables de tienda
 *   • 0 < días ≤ 20  → supervisor + responsables de tienda
 *   • días ≤ 0       → supervisor + responsables + director
 *
 * @param {object} payload
 *   - branch_id: string | null (null = todas las sucursales)
 *   - dry_run:   boolean (true = previsualizar sin enviar)
 */
export async function sendHierarchicalAlerts(payload = {}) {
  const { data } = await api.post("/api/agents/send-hierarchical-alerts", payload);
  return data;
}