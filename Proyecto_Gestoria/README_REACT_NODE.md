# ContratosVertiche22 — versión React + Node.js + FastAPI

Esta versión conserva como base los módulos de `ContratosVertiche22` y reemplaza la interfaz Streamlit por un frontend React/Vite basado en `gestoria_tramites_legales-frontend`.

## Qué se integró

- Backend Python con FastAPI en `app.py`.
- Frontend React/Vite en `frontend/`.
- OCR y bucket de Supabase conservados desde el proyecto base.
- Workflow multi-agente conservado: router, monitoreo documental, validación regulatoria, activación inteligente, email, alertas, Teams y WhatsApp.
- `compliance_chat_assistant.py` migrado de Anthropic a OpenAI usando `OPENAI_API_KEY` del `.env`.
- Endpoints para dashboard, carga/listado de documentos, monitoreo, prueba de WhatsApp/Teams, visitas de Protección Civil y chat del asistente.
- Se conservaron copias de referencia: `app_streamlit_original.py` y `compliance_chat_assistant_streamlit_original.py`.

## Estructura principal

```text
ContratosVertiche22_react_node/
├─ app.py                         # API FastAPI principal
├─ compliance_chat_assistant.py   # Asistente Verti con OpenAI
├─ agents/                        # Agentes base del proyecto
├─ services/                      # OCR, Teams, WhatsApp, Calendar, Email
├─ workflows/                     # Orquestación multi-agente
├─ schemas/                       # Modelos Pydantic
├─ dashboard/                     # Servicios de métricas
├─ frontend/                      # React + Vite + Node.js
├─ .env.example                   # Plantilla segura de variables
└─ requirements.txt
```

## Configuración

1. Copia `.env.example` a `.env`.
2. Llena al menos:

```bash
OPENAI_API_KEY=tu_api_key
SUPABASE_URL=...
SUPABASE_KEY=...
SUPABASE_BUCKET=tramites
SUPABASE_PREFIX=opcional
```

Para envío real:

```bash
TEAMS_WEBHOOK_URL=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+52...
DEFAULT_WHATSAPP=+52...
```

Si Teams/Twilio no están configurados, el backend corre en modo simulado y deja logs internos.

## Correr backend

```bash
cd ContratosVertiche22_react_node
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

API: `http://localhost:8000`

## Correr frontend React

```bash
cd ContratosVertiche22_react_node/frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

Si tu backend corre en otro puerto, crea `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## Endpoints principales

- `GET /api/health`
- `GET /api/dashboard?refresh=false`
- `GET /api/documents`
- `POST /api/documents/upload`
- `GET /api/monitoring`
- `POST /api/agents/test-notifications`
- `GET /api/pc-visits`
- `POST /api/pc-visits`
- `POST /api/assistant/chat`

## Nota de seguridad

No se incluye el archivo `.env` real en este ZIP para evitar exponer credenciales. Usa `.env.example` como plantilla.
