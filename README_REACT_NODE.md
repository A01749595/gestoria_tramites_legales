# GestoriaVertiche22 — versión React + Node.js + FastAPI

Esta versión conserva como base los módulos de `GestoriaVertiche22` y reemplaza la interfaz Streamlit por un frontend React/Vite basado en `gestoria_tramites_legales-frontend`.

## ⚠️ Cambio importante: OCR ahora es 100% local

Esta versión **ya no usa Azure Document Intelligence**. El stack de OCR
es el mismo que `GestoriaVertiche` (el proyecto de contratos):

- **PyMuPDF** (`fitz`) lee texto digital de PDFs y rasteriza páginas escaneadas.
- **Tesseract** (vía `pytesseract`) hace OCR sobre las páginas rasterizadas,
  con `lang="spa+eng"` y dos PSM (6 y 4) para quedarse con el mejor resultado.
- OpenAI sigue siendo quien extrae los campos estructurados desde el texto.

### Requisitos del sistema

Antes de instalar `requirements.txt` necesitas el binario `tesseract` y el
paquete de idioma español:

```bash
# Ubuntu / Debian / Streamlit Cloud (vía packages.txt)
sudo apt-get install -y tesseract-ocr tesseract-ocr-spa

# macOS
brew install tesseract tesseract-lang

# Verifica que esté en PATH:
tesseract --version
```

Streamlit Cloud y servicios similares leen `packages.txt`, así que ese
archivo ya está en el repo con las dos dependencias necesarias.

### Por qué este OCR es más rápido para el dashboard

- `OCR_MAX_PAGES=4`: solo procesa las primeras 4 páginas por PDF.
- Tesseract solo entra cuando la página viene "vacía" (PDF escaneado);
  los PDFs digitales se leen directo con PyMuPDF (instantáneo).
- Preprocesado de imagen ligero (gris + contraste + sharpen + binarizado).
- Estos parámetros se pueden ajustar desde `.env` sin tocar código.

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
GestoriaVertiche22_react_node/
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
# DEFAULT_WHATSAPP ahora soporta múltiples números separados por coma:
DEFAULT_WHATSAPP=+525511111111,+525522222222
# Año prioritario del proyecto (default 2026). Los PDFs en carpetas con
# ese año se procesan primero y se asume que están vigentes cuando el
# OCR no logra extraer fecha del texto.
PRIORITY_YEAR=2026
```

Si Teams/Twilio no están configurados, el backend corre en modo simulado y deja logs internos.

### WhatsApp: solución de problemas comunes

El sandbox de Twilio (`+1 415 523 8886`) tiene tres limitaciones que casi
siempre causan el primer fallo:

1. **El destinatario no envió `join <tu_keyword>` al número del sandbox.**
   Solo se entregan mensajes a usuarios que hicieron opt-in. Error Twilio
   `63015`. Solución: cada destinatario manda `join <keyword>` por WhatsApp
   al `+1 415 523 8886` (la keyword sale en la consola de Twilio).
2. **Pasaron más de 24h desde el último mensaje del usuario** y el body
   no es una plantilla. Error `63016`. Solución: pasar `content_sid` (SID
   de una plantilla aprobada en Twilio Content API) en vez de `body`.
3. **Número en formato incorrecto.** Debe ser E.164: `+52` + lada + número
   sin espacios ni guiones. Error `21211`. El backend valida y rechaza
   antes de llamar a Twilio para no quemar tu cuota.

Para producción real (sin las limitaciones del sandbox), registra tu propio
número en Meta Business y úsalo como `TWILIO_WHATSAPP_NUMBER`. Twilio
agrega ~$0.005 USD de markup por mensaje sobre la tarifa de Meta, así
que para volúmenes altos puede convenir mover a Meta Cloud API directo.

### Documentos sin fecha: fallback por año de carpeta

Cuando OpenAI no logra extraer `expiration_date` del texto OCR, el backend
busca el año dentro de la ruta del PDF en Supabase (`2026/...`,
`tramites/2025/...`, etc.) y le asigna `31 de diciembre del año detectado`
como vencimiento estimado. El estado resultante:

| Carpeta detectada | Estado asignado            | Razón                            |
|-------------------|----------------------------|----------------------------------|
| 2026 / año actual | `valid` (vigente)          | Vence al cierre del año en curso |
| 2025 / año-1      | `close_to_expiration` o `expired` según mes | Año anterior cerrado |
| 2024 o anterior   | `expired`                  | Año previo ya vencido            |
| Sin año en la ruta | `incomplete` (Sin fecha)  | No se puede inferir              |

Los documentos clasificados así llevan `metadata.expiration_inferred_from_folder = true`
y `metadata.folder_year`; el frontend muestra una etiqueta `carpeta 2026`
al lado del vencimiento para que sepas que vino del fallback.

## Correr backend

```bash
cd GestoriaVertiche22_react_node
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
cd GestoriaVertiche22_react_node/frontend
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
- `POST /api/agents/send-expired-alert` — alerta de vencidos (acepta varios correos separados por coma)
- `GET /api/pc-visits`
- `POST /api/pc-visits`
- `POST /api/assistant/chat`

### Trámites por sucursal (llenado manual)

- `GET /api/tramites` — todas las sucursales con su % de cumplimiento
- `GET /api/tramites/resumen` — resumen compacto para el dashboard
- `POST /api/tramites/sucursal` — crea o actualiza una sucursal
- `DELETE /api/tramites/sucursal/{tramite_id}` — elimina una sucursal
- `POST /api/tramites/reset` — restaura los datos al documento original

Los datos se guardan en `tramites_data.json` en la raíz del proyecto (se
puede mover con la variable `TRAMITES_DATA_FILE`). La primera vez se
precarga con los 21 trámites extraídos de `TRAMITES.docx`. El % de
cumplimiento se calcula sobre los 5 trámites requeridos (Aviso de
funcionamiento, Uso de suelo, Anuncio, Protección Civil, Licencia
Ambiental), evaluando la columna de vigencia 2026.

### Alertas segmentadas

- `GET /api/agents/segments` — valores disponibles (sucursales,
  municipios, estados) con conteo de vencidos
- `POST /api/agents/send-segmented-alert` — alerta de vencidos filtrada
  por sucursal / municipio / estado. Los campos `emails` y `whatsapp`
  aceptan varios destinatarios separados por coma; si se dejan vacíos,
  se usan los asignados a las sucursales afectadas.

## Páginas del frontend

- **Dashboard** — KPIs, gráficas y tabs: Resumen, Por estado, Por
  municipio, Por sucursal y **Trámites por sucursal** (porcentajes de
  cumplimiento). Todas las tablas tienen buscador.
- **Documentos** — carga de PDFs al bucket y listado con búsqueda.
- **Trámites** — captura manual de la vigencia de trámites por sucursal.
- **Agentes** — pruebas de WhatsApp/Teams, alerta de vencidos y
  **alertas segmentadas**.
- **Asistente** — chat de compliance.

## Nota de seguridad

No se incluye el archivo `.env` real en este ZIP para evitar exponer credenciales. Usa `.env.example` como plantilla.
