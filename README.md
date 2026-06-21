# Multi-Agent Legal & Regulatory Compliance Platform

> Automated tracking, OCR ingestion, and multi-channel alerting for the operating permits.

---

## Overview

Gestio is a full-stack platform that keeps a commercial chain compliant with the municipal, state, and federal permits that every branch needs to operate legally in Mexico. The system ingests permit PDFs, reads them with a fully local OCR pipeline, extracts the relevant legal fields with an LLM, classifies each document by its expiration status, and orchestrates a set of specialized agents that notify the right people — store managers, supervisors, and directors — through email, Microsoft Teams, WhatsApp, and Google Calendar before a permit lapses.

The project pairs a **FastAPI** backend (multi-agent workflow, OCR, Supabase storage, notifications, and an OpenAI-powered assistant) with a **React + Vite** frontend (dashboard, document upload, manual permit capture, monitoring, branch map, and a compliance chatbot). It replaces an earlier Streamlit prototype and removes the original Azure dependency in favor of an on-premise OCR stack.

The five mandatory permits tracked for every branch are: *Aviso de funcionamiento*, *Uso de suelo*, *Anuncio*, *Protección Civil (Visto Bueno)*, and *Licencia Ambiental*.

---

## Business Problem

A retail chain with hundreds of branches must hold and continuously renew several operating permits per location. Each permit has its own issuing authority, folio, issue date, and expiration date, and the rules vary by state and municipality.

Managing this manually creates concrete operational and legal risk:

- **Permits expire silently.** Without a central, date-aware system, an expired *Protección Civil* clearance or *Licencia Ambiental* can go unnoticed until an inspection.
- **Documents are heterogeneous and messy.** Permits arrive as digital PDFs and as scanned images, with folios and dates written in many formats (numeric, long-form Spanish, date ranges). Reading them by hand does not scale.
- **Accountability is diffuse.** When something is about to lapse, it is unclear who should be alerted and how urgently — the store, the regional supervisor, or the director.
- **Compliance status is invisible.** Leadership has no single view of how compliant each branch, municipality, or state is at a given moment.

---

## Business Objectives

1. **Centralize** every branch's permits and their validity dates in one auditable system.
2. **Automate ingestion** so a manager can upload a PDF and have the folio, issue date, expiration date, and issuing authority extracted automatically.
3. **Classify risk** by translating raw dates into actionable statuses (valid, close to expiration, expired, missing, incomplete, unreadable).
4. **Escalate intelligently** — alert the right organizational tier based on how close a permit is to expiring.
5. **Notify across the channels people actually use** — email, Teams, WhatsApp, and calendar — with graceful fallback to a simulated mode when credentials are absent.
6. **Give leadership visibility** through a dashboard with compliance percentages segmented by branch, municipality, and state.
7. **Lower the support burden** with a Spanish-language assistant ("Verti") that answers questions about alerts, expirations, and compliance in plain language.

---

## Solution Architecture

The system is organized in three layers: a React frontend, a FastAPI orchestration backend with a multi-agent core, and a set of external services (Supabase, OpenAI, and notification providers).

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND — React 19 + Vite                                            │
│  Dashboard · Documentos · Trámites · Monitoreo · Asistente · Mapa      │
│  (axios → REST · recharts charts · react-leaflet map · JWT auth)       │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │  REST / JSON
┌───────────────────────────────▼──────────────────────────────────────┐
│  BACKEND — FastAPI (app.py)                                            │
│  Auth (JWT · bcrypt · SQLite)   ·   Dashboard service   ·   Assistant  │
│                                                                        │
│   ComplianceWorkflow  (orchestrator)                                   │
│   ┌──────────────┬───────────────────┬───────────────────────────┐    │
│   │ Router Agent │ Document Monitor  │ Regulatory Validation     │    │
│   │ Intelligent  │ Email Automation  │ Renewal Alert             │    │
│   │ Activation   │                   │                           │    │
│   └──────────────┴───────────────────┴───────────────────────────┘    │
│                                                                        │
│   Services: OCR · Email(SMTP) · Teams · WhatsApp · Calendar · Trámites │
└───────┬───────────────────┬───────────────────┬───────────────────────┘
        │                   │                   │
┌───────▼───────┐  ┌────────▼────────┐  ┌───────▼─────────────────────┐
│ Supabase      │  │ OpenAI          │  │ Notification providers      │
│ Storage +     │  │ Field extract   │  │ SMTP · Teams webhook ·      │
│ OCR queue     │  │ + chat (Verti)  │  │ Twilio/CallMeBot · GCal     │
└───────────────┘  └─────────────────┘  └─────────────────────────────┘
                 ▲
        ┌────────┴─────────┐
        │ ocr_realtime_    │  Background worker: listens on Supabase
        │ worker.py        │  pending_ocr_queue (pg_notify + polling)
        └──────────────────┘
```

**The six agents and their roles**

| Agent | Responsibility |
|-------|----------------|
| **Router** | Analyzes each incoming request (upload, status check) and decides which specialized agent handles it, assigning an urgency level. |
| **Document Monitoring** | Extracts folio, dates, and issuing authority from OCR text (rich Spanish-language regex catalogs) and classifies document status. |
| **Regulatory Validation** | Checks each branch against the legal-requirements matrix per state/municipality and computes a compliance score and legal-risk level. |
| **Intelligent Activation** | Orchestrates the response — runs critical / high / medium / standard workflows depending on urgency. |
| **Email Automation** | Generates and sends templated emails for expired, missing, and soon-to-expire documents, plus compliance reports. |
| **Renewal Alert** | Fans out alerts across Google Calendar, Teams, WhatsApp, and email, with per-channel formatting. |

---

## End-to-End Workflow

1. **Authentication.** A user registers/logs in; the backend issues a JWT (bcrypt-hashed credentials stored in a local SQLite database).
2. **Upload.** A permit PDF/image is uploaded through the *Documentos* page to a Supabase Storage bucket. Supported types are queued for OCR.
3. **OCR ingestion (local).** PyMuPDF first tries to read digital text directly (instant, free). If a page is "sparse" — i.e. a scanned image — it is rasterized and passed to Tesseract (`spa+eng`, multiple PSM passes, light preprocessing). A real-time worker (`ocr_realtime_worker.py`) consumes Supabase's `pending_ocr_queue` via `LISTEN/pg_notify` with a 30-second polling backup, so nothing is left unprocessed.
4. **Field extraction.** OpenAI parses the OCR text into structured fields (folio, issue date, expiration date, issuing authority, RFC/CURP when present).
5. **Date fallback.** When no expiration date can be extracted, the backend infers one from the document's folder year in Supabase (e.g. `2026/...`), assigning December 31 of that year and tagging the record so the UI shows a "carpeta 2026" label.
6. **Classification.** Each document is labeled `valid`, `close_to_expiration` (≤ 45 days), `expired`, `missing`, `unreadable`, `incomplete`, or `pending_review`.
7. **Routing & validation.** The Router and Regulatory Validation agents determine urgency and compute branch-level compliance against the requirements matrix.
8. **Escalation & alerts.** The Intelligent Activation and Renewal Alert agents notify the appropriate organizational tier:
   - **20 < days ≤ 40** → store managers
   - **0 < days ≤ 20** → supervisor + store managers
   - **days ≤ 0** → director + supervisor + store managers
9. **Visibility.** The dashboard aggregates compliance KPIs by branch, municipality, and state; the *Trámites* page lets staff capture permit validity manually; "Verti" answers natural-language questions about the current state.

---

## Technology Stack

**Backend**
- Python · FastAPI · Uvicorn · Pydantic (schemas & validation)
- SQLAlchemy + SQLite (user store) · passlib/bcrypt · PyJWT (auth)
- OpenAI SDK (field extraction + assistant, `gpt-4o-mini` default)
- Supabase (object storage + real-time OCR queue)

**OCR pipeline (100% local, no Azure)**
- PyMuPDF (`fitz`) — digital text extraction & page rasterization
- Tesseract via `pytesseract` (`spa+eng`) · Pillow — image preprocessing

**Notifications & integrations**
- SMTP email · Microsoft Teams (incoming webhook)
- WhatsApp via Twilio and/or CallMeBot · Google Calendar
- All providers degrade to a logged "simulated" mode when unconfigured

**Frontend**
- React 19 · Vite · React Router
- axios (API client) · recharts (charts) · react-leaflet + Leaflet (branch map)
- lucide-react (icons) · jwt-decode · OGL (animated background)

**Data & analysis**
- pandas · numpy · python-dateutil for date logic and dashboard aggregation

---

## Key Technical Features

- **Hybrid local OCR.** Digital PDFs are read instantly; only genuinely scanned pages fall through to Tesseract, with tunable `OCR_MAX_PAGES`, zoom/DPI, and a sparse-text threshold — all configurable from `.env` without code changes.
- **Robust Spanish field extraction.** The monitoring agent ships extensive regex catalogs for folios (`folio`, `oficio`, `expediente`, `permiso no.`…), mixed date formats (numeric and long-form Spanish, including "a los 15 días del mes de…"), validity-range parsing, and a catalog of Mexican issuing authorities (SAT, IMSS, Protección Civil, etc.).
- **Real-time, fault-tolerant ingestion.** A dedicated worker combines `pg_notify` for sub-second latency with periodic polling so failed or missed items are retried.
- **Folder-year inference** as a safety net for undated documents, with explicit metadata flags so the inference is transparent in the UI.
- **Tiered escalation logic** that maps days-to-expiration onto organizational responsibility.
- **Graceful degradation.** Missing Teams/Twilio/SMTP credentials never crash the system; the backend simulates delivery and keeps internal logs.
- **Segmented & hierarchical alerting** by branch, municipality, or state, with multi-recipient support.
- **Compliance scoring** computed over the five required permits per branch, surfaced as percentages on the dashboard.
- **Conversational layer.** "Verti," an OpenAI-backed Spanish assistant, contextualizes alerts, expirations, and Protección Civil visits in plain language.
- **In-app manual capture** of permit validity, persisted to `tramites_data.json` and seeded from the source `TRAMITES.docx`.

---

## Impact Metrics

> These are the operational metrics the platform is designed to produce and track. They define what "good" looks like for the system rather than results from a measured production deployment.

- **Branch compliance rate (%)** — share of the five required permits valid per branch, aggregated by branch, municipality, and state.
- **Documents by status** — counts of valid / close-to-expiration / expired / missing / incomplete / unreadable across the portfolio.
- **Days-to-expiration distribution** — feeds the 45/40/20/15-day alert thresholds.
- **Alert coverage** — number of notifications dispatched per channel and per escalation tier.
- **OCR throughput & latency** — documents processed at startup vs. via the real-time worker (sub-second notify latency target).
- **Extraction completeness** — proportion of uploads from which dates and folios are successfully extracted vs. those needing folder-year fallback.

