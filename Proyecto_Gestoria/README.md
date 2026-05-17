# ContratosVertiche · Dashboard de Compliance

Aplicación Streamlit única que extrae datos de contratos en PDF (Supabase),
los procesa con un sistema multiagente de cumplimiento normativo, y los
muestra en un dashboard con cobertura por los 32 estados de México.

> **Sin chatbot.** Esta versión es solo dashboard + carga + monitoreo.

---

## Arquitectura

```
ContratosVertiche-main/
├── app.py                       ← ÚNICA app Streamlit (3 tabs)
├── requirements.txt
├── .env.example
│
├── schemas/
│   └── schemas.py               ← Pydantic: Branch, Document, etc.
│
├── agents/                      ← Sistema multiagente de compliance
│   ├── compliance_router_agent.py
│   ├── compliance_document_monitoring_agent.py
│   ├── compliance_regulatory_validation_agent.py
│   ├── compliance_intelligent_activation_agent.py
│   ├── compliance_email_automation_agent.py
│   ├── compliance_renewal_alert_agent.py
│   └── *_agent.py               ← Shims con nombres cortos
│
├── workflows/
│   └── compliance_workflow.py   ← Orquestador (sin Azure)
│
├── dashboard/
│   └── dashboard_service.py     ← Métricas y agregaciones
│
├── services/                    ← Integraciones (real/simulado)
│   ├── ocr_service.py           ← PyMuPDF local (sin Azure)
│   ├── email_service.py         ← SMTP
│   ├── calendar_service.py      ← Google Calendar
│   ├── teams_service.py         ← Microsoft Teams webhook
│   └── whatsapp_service.py      ← Twilio WhatsApp
│
└── config/
    └── config.py                ← Lee .env y arma config global
```

---

## Las 3 secciones del app.py

1. **📊 Dashboard** — KPIs, mapa de los 32 estados (alimentado por el
   `DashboardService` sobre los datos extraídos), distribución por status,
   tipos de documento, alertas críticas/altas/medias. Botón "Refrescar"
   para reprocesar.

2. **📤 Subir documentos** — carga PDFs al bucket de Supabase. Opción de
   sobreescribir y de invalidar la caché del dashboard.

3. **🔍 Monitoreo de agentes** — estado en vivo de cada servicio
   (REAL/SIMULADO), historial de extracciones del pipeline RAG con tasa de
   éxito, y bandejas de envío (emails, eventos de calendario, mensajes de
   Teams/WhatsApp, runs de OCR).

---

## Pipeline de extracción (sin Azure OCR)

Para cada PDF del bucket:

1. `bucket.download(path)` → bytes
2. `PyMuPDF` → texto plano
3. `OpenAI` con `response_format=json_object` → JSON estructurado
   (`branch_name`, `state`, `expiration_date`, `risk_level`, …)
4. Mapeo a `Branch` + `Document` (Pydantic, validados)
5. `DashboardService` agrega métricas

Los resultados se cachean en `st.session_state.compliance_data`.

---

## Setup

### 1. Instalar

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt
```

### 2. Configurar `.env`

```bash
cp .env.example .env
# editar y rellenar credenciales
```

**Mínimo necesario para que el dashboard funcione:**
- `OPENAI_API_KEY`
- `SUPABASE_URL` + `SUPABASE_KEY` + `SUPABASE_BUCKET`

**Opcionales** (en modo SIMULADO si vacíos):
- `SMTP_*` → notificaciones por email
- `GOOGLE_CALENDAR_*` → eventos de vencimiento
- `TEAMS_WEBHOOK_URL` → mensajes en Teams
- `TWILIO_*` → WhatsApp

### 3. Arrancar

```bash
streamlit run app.py
```

---

## Modo SIMULADO

Cada servicio sin credenciales **no falla**: loggea lo que habría enviado
y lo expone en el tab de Monitoreo. Esto permite desarrollar y demostrar
el sistema completo sin contratar SMTP, Calendar, Teams ni Twilio.

---

## ⚠️ Seguridad

- No comites `.env` (ya está en `.gitignore`).
- Rota inmediatamente cualquier `SUPABASE_KEY` que haya estado hardcodeada en
  versiones previas.
- Esta versión carga TODAS las credenciales por variables de entorno.

---

## Made with Bob · Tec de Monterrey CEM
