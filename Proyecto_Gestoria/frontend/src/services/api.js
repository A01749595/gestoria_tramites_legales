import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({ baseURL: API_BASE, timeout: 120000 });

export async function getHealth() {
  const { data } = await api.get("/api/health");
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
