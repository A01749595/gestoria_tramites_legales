import argparse
import csv
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

DELAY_MIN = 2.0
DELAY_MAX = 5.0
TIMEOUT   = 25
MAX_RETRY = 3

HEADERS = {
    "User-Agent":                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":                    "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language":           "es-MX,es;q=0.9",
    "Accept-Encoding":           "gzip, deflate, br",
    "Connection":                "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

LF  = "licencia_funcionamiento"
US  = "uso_suelo"
PC  = "proteccion_civil"
AMB = "ambiental"
NA  = "no_adeudo"

TIENDAS: dict[str, tuple[str, str, str]] = {
    "T-001": ("Ciudad de México",  "CDMX",               "San Antonio Abad"),
    "T-003": ("Ciudad de México",  "CDMX",               "Portales"),
    "T-007": ("Estado de México",  "Tlalnepantla",        "Tlalnepantla"),
    "T-008": ("Estado de México",  "Chalco",              "Chalco"),
    "T-014": ("Puebla",            "Puebla",              "Puebla Outlet"),
    "T-015": ("Puebla",            "Atlixco",             "Atlixco"),
    "T-016": ("Puebla",            "Puebla",              "Puebla Centro"),
    "T-017": ("Puebla",            "Izúcar de Matamoros", "Izúcar"),
    "T-018": ("Tlaxcala",          "Huamantla",           "Huamantla"),
    "T-019": ("Veracruz",          "Orizaba",             "Orizaba"),
    "T-022": ("Veracruz",          "Veracruz",            "Veracruz"),
    "T-023": ("Guerrero",          "Chilpancingo",        "Chilpancingo"),
    "T-024": ("Michoacán",         "Zamora",              "Zamora"),
    "T-025": ("Michoacán",         "Uruapan",             "Uruapan"),
    "T-028": ("Yucatán",           "Mérida",              "Mérida"),
    "T-030": ("Veracruz",          "Tuxpan",              "Tuxpan"),
    "T-032": ("Chiapas",           "Tuxtla Gutiérrez",    "Tuxtla Gutiérrez"),
    "T-034": ("Tabasco",           "Villahermosa",        "Villahermosa"),
    "T-035": ("Morelos",           "Cuautla",             "Cuautla Bravos"),
    "T-037": ("Tlaxcala",          "Apizaco",             "Apizaco"),
    "T-038": ("Estado de México",  "Toluca",              "Toluca"),
}

@dataclass
class Fuente:
    estado:    str
    municipio: str
    doc_tipo:  str
    url:       str
    parser:    str = "auto"
    selector:  str = "body"
    tiendas:   list = field(default_factory=list)

FUENTES: list[Fuente] = [
    Fuente("Ciudad de México", "CDMX",              US, "https://www.cdmx.gob.mx/public/InformacionTramite.xhtml?idTramite=549",  parser="playwright", selector="#contenidoForm, #contenido, .tramite-container, main", tiendas=["T-001", "T-003"]),
    Fuente("Ciudad de México", "CDMX",              PC, "https://www.proteccioncivil.cdmx.gob.mx/servicios/servicio/tramites-y-servicios",              selector="#contenido, main, .container", tiendas=["T-001", "T-003"]),
    Fuente("Chiapas",          "Tuxtla Gutiérrez",  LF, "https://tramites.tuxtla.gob.mx/visualizar/241",                                                parser="playwright", selector=".tramite-detalle, .detalle, #tramite, main, article", tiendas=["T-032"]),
    Fuente("Chiapas",          "Tuxtla Gutiérrez",  US, "https://tramites.tuxtla.gob.mx/visualizar/247",                                                parser="playwright", selector=".tramite-detalle, .detalle, #tramite, main, article", tiendas=["T-032"]),
    Fuente("Chiapas",          "Tuxtla Gutiérrez",  PC, "https://proteccioncivil.tuxtla.gob.mx/Dictamen-de-cumplimiento-medidas-de-pc",                 parser="playwright", tiendas=["T-032"]),
    Fuente("Puebla",           "Puebla",            LF, "https://experta.pueblacapital.gob.mx/web/fichaAsunto.do?opcion=0&asas_ide_asu=2470",           parser="playwright", tiendas=["T-014", "T-016"]),
    Fuente("Puebla",           "Puebla",            US, "https://experta.pueblacapital.gob.mx/web/fichaAsunto.do?opcion=0&asas_ide_asu=184",            parser="playwright", tiendas=["T-014", "T-016"]),
    Fuente("Puebla",           "Puebla",            PC, "https://experta.pueblacapital.gob.mx/web/fichaAsunto.do?opcion=0&asas_ide_asu=2490",           parser="playwright", tiendas=["T-014", "T-016"]),
    Fuente("Tabasco",          "Villahermosa",      LF, "https://tramites.villahermosa.gob.mx/tramites/e45fcc3d-7515-4a02-a9c1-0b72ddb3138e",          parser="playwright", tiendas=["T-034"]),
    Fuente("Tabasco",          "Villahermosa",      US, "https://tramites.villahermosa.gob.mx/tramites/6a36b258-8aa8-486f-a363-63dc033c5665",          parser="playwright", tiendas=["T-034"]),
    Fuente("Tabasco",          "Villahermosa",      PC, "https://tramites.villahermosa.gob.mx/tramites/b082d02d-9ad8-4c5f-8eeb-fa68e66f372c",          parser="playwright", tiendas=["T-034"]),
    Fuente("Veracruz",         "Veracruz",          LF, "https://miveracruz.veracruzmunicipio.gob.mx/ver_ficha/uNAZV1LdxmFylzzNHCeL",                  tiendas=["T-022"]),
    Fuente("Veracruz",         "Veracruz",          US, "https://miveracruz.veracruzmunicipio.gob.mx/ver_ficha/d8ea5630-f2c2-11ea-8190-43c3fa7160b6",  tiendas=["T-022"]),
    Fuente("Veracruz",         "Veracruz",          PC, "https://miveracruz.veracruzmunicipio.gob.mx/ver_ficha/804abe10-e1dd-11ea-8b77-59121d5d03ea",  tiendas=["T-022"]),
    Fuente("Yucatán",          "Mérida",            LF, "https://isla.merida.gob.mx/serviciosinternet/tramites/detalle/778",                            tiendas=["T-028"]),
    Fuente("Yucatán",          "Mérida",            US, "https://isla.merida.gob.mx/serviciosinternet/tramites/detalle/534",                            tiendas=["T-028"]),
    Fuente("Yucatán",          "Mérida",            PC, "https://isla.merida.gob.mx/serviciosinternet/tramites/detalle/493",                            tiendas=["T-028"]),
]


def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Faltan SUPABASE_URL o SUPABASE_KEY en .env")
    return create_client(url, key)

def upsert_estado(sb, nombre):
    sb.table("estados").upsert({"nombre": nombre}, on_conflict="nombre").execute()
    return sb.table("estados").select("id").eq("nombre", nombre).single().execute().data["id"]

def upsert_municipio(sb, estado_id, nombre):
    sb.table("municipios").upsert({"estado_id": estado_id, "nombre": nombre}, on_conflict="estado_id,nombre").execute()
    return sb.table("municipios").select("id").eq("estado_id", estado_id).eq("nombre", nombre).single().execute().data["id"]

def insert_tramite(sb, municipio_id, data):
    payload = {k: v for k, v in {
        "municipio_id":        municipio_id,
        "doc_tipo":            data.get("doc_tipo"),
        "homoclave":           data.get("homoclave"),
        "nombre_tramite":      data.get("nombre_tramite"),
        "descripcion":         data.get("descripcion"),
        "dependencia":         data.get("dependencia"),
        "modalidad":           data.get("modalidad"),
        "vigencia":            data.get("vigencia"),
        "costo":               data.get("costo"),
        "tiempo_respuesta":    data.get("tiempo_respuesta"),
        "afirmativa_ficta":    data.get("afirmativa_ficta", False),
        "url_fuente":          data.get("url_fuente"),
        "fecha_actualizacion": data.get("fecha_actualizacion"),
        "raw_text":            (data.get("raw_text") or "")[:5000],
    }.items() if v is not None}
    return sb.table("tramites").insert(payload).execute().data[0]["id"]

def insert_requisitos(sb, tramite_id, requisitos):
    if not requisitos:
        return
    rows = [{
        "tramite_id":  tramite_id,
        "orden":       i + 1,
        "texto":       r["texto"],
        "presentacion":r.get("presentacion"),
        "num_copias":  r.get("num_copias"),
        "obligatorio": r.get("obligatorio", True),
        "condicion":   r.get("condicion"),
    } for i, r in enumerate(requisitos)]
    sb.table("requisitos").insert(rows).execute()

def insert_ubicaciones(sb, tramite_id, ubicaciones):
    if not ubicaciones:
        return
    rows = [{
        "tramite_id": tramite_id,
        "nombre":     u.get("nombre"),
        "direccion":  u.get("direccion"),
        "telefono":   u.get("telefono"),
        "horario":    u.get("horario"),
        "dias":       u.get("dias"),
    } for u in ubicaciones]
    sb.table("ubicaciones").insert(rows).execute()

def log_error_db(sb, fuente, mensaje):
    sb.table("scraper_errores").insert({
        "estado": fuente.estado, "municipio": fuente.municipio,
        "doc_tipo": fuente.doc_tipo, "url": fuente.url, "mensaje": mensaje,
    }).execute()


def fetch_requests(url: str, session: requests.Session) -> Optional[str]:
    for i in range(1, MAX_RETRY + 1):
        try:
            import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = session.get(url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True, verify=False)
            if r.status_code == 200:
                return r.text
            log.warning(f"  HTTP {r.status_code} (intento {i})")
        except requests.RequestException as e:
            log.warning(f"  {e} (intento {i})")
        time.sleep(2 ** i + random.uniform(0, 1))
    return None

def fetch_playwright(url: str) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="es-MX",
                viewport={"width": 1280, "height": 900},
            ).new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=35_000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.error(f"  Playwright: {e}")
        return None

def fetch(fuente: Fuente, session: requests.Session) -> Optional[str]:
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    if fuente.parser == "playwright":
        return fetch_playwright(fuente.url)
    if fuente.parser == "pdf":
        return fetch_requests(fuente.url, session)
    html = fetch_requests(fuente.url, session)
    if not html:
        html = fetch_playwright(fuente.url)
        return html
    from bs4 import BeautifulSoup as _BS
    text_preview = _BS(html, "lxml").get_text(" ", strip=True)
    if len(text_preview) < 300:
        log.info("  HTML con poco texto, reintentando con Playwright…")
        html = fetch_playwright(fuente.url) or html
    return html


def _re(pattern: str, text: str, group: int = 1) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    try:
        val = m.group(group).strip()
    except IndexError:
        val = m.group(0).strip()
    val = re.sub(r'\s+', ' ', val)
    return val[:500] if val else None

def _clean(s):
    if not s:
        return s
    s = re.sub(r"^(?:del tr[aá]mite|del documento|o Entidad|de atenci[oó]n)[:\s]+", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()

def extraer_campos(text: str) -> dict:
    homoclave = _clean(
        _re(r"Homoclave[:\s]+([A-Z0-9/\-]{5,30})", text) or
        _re(r"\b([A-Z]{2,6}-[A-Z]+-\d+)\b", text) or
        _re(r"\b(T-[A-Z]+/[A-Z]+/\d+)\b", text)
    )
    fecha = (
        _re(r"(?:Fecha (?:de |[uú]ltima )?actualizaci[oó]n)[:\s]*\n?\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", text) or
        _re(r"Fecha[:\s]+(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", text)
    )
    descripcion = _clean(
        _re(r"(?:Descripci[oó]n[:\s]*\n|Objetivo del tr[aá]mite[:\s]*\n|Descripci[oó]n del tr[aá]mite[:\s]*\n)(.+?)(?=\nBeneficio|\nFundamento|\nTiempo|\nVigencia|\nQu[eé]\s*Obtengo|\nCosto|\nModalidad|\nDependencia|\nDocumentaci[oó]n|\Z)", text) or
        _re(r"(?:Descripci[oó]n|Objetivo)[:\s]+([^\n]{20,500})", text)
    )
    if descripcion and len(descripcion) > 600:
        descripcion = descripcion[:600]
    modalidad   = _re(r"Modalidad[:\s]+([^\n]{3,50})", text)
    tiempo      = _clean(
        _re(r"Tiempo de respuesta m[aá]ximo\s*\n\s*([^\n]{2,50})", text) or
        _re(r"Tiempo de (?:resoluci[oó]n|respuesta)[:\s]+([^\n]{2,60})", text) or
        _re(r"(\d+\s+(?:d[ií]as?\s+h[aá]biles?|horas?|minutos?))", text)
    )
    vigencia    = _clean(
        _re(r"Vigencia\s*\n\s*([^\n]{2,60})", text) or
        _re(r"Vigencia[:\s]+([^\n]{2,60})", text) or
        _re(r"Vigencia del (?:documento|tr[aá]mite)[:\s]+([^\n]{2,60})", text)
    )
    costo = (
        _re(r"(?:^|\n)Costo\s*\n\s*(\$[^\n]{2,120})", text) or
        _re(r"Costo[:\s]+(\$[^\n]{2,120})", text) or
        _re(r"(\$\s*[\d,\.]+\s*(?:mxn|MXN|pesos|m\.n\.)?)", text)
    )
    ficta       = bool(re.search(r"afirmativa ficta", text, re.IGNORECASE))
    dependencia = _clean(
        _re(r"(?:Unidad administrativa responsable[^\n]*\n\s*|Dependencia\s+o\s+Entidad[:\s]*\n\s*|Dependencia[:\s]+|Área responsable[:\s]+)([^\n]{5,120})", text) or
        _re(r"Direcci[oó]n de ([A-ZÁÉÍÓÚÑ][^\n]{4,80})", text)
    )
    nombre = _re(
        r"(?m)^(?:Apertura|Solicitud|Licencia|Constancia|Certificado|Visto Bueno|Modificaci[oó]n|Dictamen|Permiso|Autorizaci[oó]n|Gesti[oó]n|Registro|Renovaci[oó]n|Tr[aá]mite)[^\n]{4,120}",
        text,
    )
    return {
        "homoclave":           homoclave,
        "fecha_actualizacion": fecha,
        "descripcion":         descripcion,
        "modalidad":           modalidad,
        "tiempo_respuesta":    tiempo,
        "vigencia":            vigencia,
        "costo":               costo,
        "afirmativa_ficta":    ficta,
        "dependencia":         dependencia,
        "nombre_tramite":      nombre,
    }

def _dedup(reqs: list[dict]) -> list[dict]:
    seen = set()
    out  = []
    for r in reqs:
        key = r["texto"][:80].lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out

def extraer_requisitos(soup: BeautifulSoup, text: str) -> list[dict]:
    requisitos = []

    bloques = soup.find_all(
        lambda t: t.name in ("div", "section", "li") and
        t.get("class") and
        any(c in " ".join(t.get("class", [])).lower() for c in ("documento", "requisito", "req-", "document"))
    )
    LABEL_RE = re.compile(
        r'^(?:Presentaci[oó]n|Copias?\s+requeridas?|N[uú]mero\s+de\s+copias?|'
        r'Original(?:es)?|En\s+l[ií]nea|Presencial)\s*:?\s*$', re.IGNORECASE,
    )
    if bloques:
        for b in bloques:
            titulo   = b.find(["strong", "b", "h3", "h4"])
            titulo_t = titulo.get_text(strip=True) if titulo else ""
            if LABEL_RE.match(titulo_t):
                titulo = None
            if titulo:
                texto = titulo_t
            else:
                block_lines = [
                    l.strip() for l in b.get_text("\n", strip=True).splitlines()
                    if l.strip() and len(l.strip()) > 8 and not LABEL_RE.match(l.strip())
                ]
                texto = block_lines[0][:200] if block_lines else ""
            if len(texto) < 10 or LABEL_RE.match(texto):
                continue
            desc_tag = b.find("p", string=lambda s: s and "presentación" not in s.lower() and "copias" not in s.lower() and len(s.strip()) > 10)
            if desc_tag:
                texto = f"{texto}: {desc_tag.get_text(strip=True)}"
            pres     = _re(r'Presentaci[oó]n[:\s]+([^\n]+)', b.get_text("\n"))
            copias_m = re.search(r'Copias requeridas\s*\n?\s*(\d+)', b.get_text("\n"))
            obl      = not any(w in texto.lower() for w in ["en su caso", "si aplica", "podrían", "opcional", "cuando aplique"])
            cond     = _re(r'(?:en su caso|si aplica|cuando aplique)[^\n]*', texto.lower()) if not obl else None
            requisitos.append({
                "texto":        texto,
                "presentacion": pres,
                "num_copias":   int(copias_m.group(1)) if copias_m else None,
                "obligatorio":  obl,
                "condicion":    cond,
            })
        valid = [r for r in requisitos if len(r["texto"]) >= 15 and not LABEL_RE.match(r["texto"])]
        if len(valid) >= max(1, len(requisitos) * 0.4):
            return _dedup(valid)

    req_section = None
    for tag in soup.find_all(["h2", "h3", "h4", "strong", "b", "p", "div"]):
        if re.search(
            r'requisito|documentos?\s+(?:necesario|requerido|a\s+presentar|solicitado)|'
            r'qu[eé]\s+necesito|documentaci[oó]n\s+(?:a\s+adjuntar|requerida|necesaria)|'
            r'lo\s+que\s+necesitas?|para\s+realizar\s+este\s+tr[aá]mite',
            tag.get_text(), re.IGNORECASE,
        ):
            req_section = tag
            break

    if req_section:
        container = req_section.find_next(["ul", "ol", "div", "table"])
        if container:
            for item in container.find_all("li"):
                texto     = item.get_text(" ", strip=True)
                if len(texto) < 10:
                    continue
                parent_li = item.find_parent("li")
                cond_src  = parent_li.get_text(" ", strip=True)[:100] if parent_li else ""
                is_cond   = any(w in texto.lower() or w in cond_src.lower() for w in ["en caso de", "si aplica", "podrían", "opcional", "cuando aplique", "de ser necesario"])
                cond      = None
                if is_cond:
                    src   = cond_src if cond_src else texto
                    m     = re.search(r'(?:En caso de[^:]+|si aplica[^:]+)', src, re.IGNORECASE)
                    cond  = m.group(0).strip() if m else src[:80]
                requisitos.append({"texto": texto, "obligatorio": not is_cond, "condicion": cond})
            if requisitos:
                return _dedup(requisitos)

    FIN_RE = re.compile(
        r'(Criterios\s+de\s+resoluci[oó]n|Ubicaci[oó]n\s*\n|Unidad\s+administrativa|'
        r'D[oó]nde\s+y\s+cu[aá]ndo|Pasos\s+a\s+seguir|Fundamento\s+Jur[ií]dico|'
        r'Marco\s+Jur[ií]dico|Fundamento\s+Legal|Procedimiento(?:\s+del\s+tr[aá]mite)?'
        r'|\bArt[ií]culo\s+\d+\s+[A-Z]|\bObservaciones\s+Adicionales\b|Servidores?\s+p[uú]blic)',
        re.IGNORECASE,
    )
    inicio = re.search(
        r'(El\s+tr[aá]mite\s+requiere|Documentos?\s+(?:o\s+)?requisitos|'
        r'Qu[eé]\s+necesito|Documentaci[oó]n\s+(?:a\s+adjuntar|requerida|necesaria)|'
        r'Documentos?\s+(?:requeridos?|a\s+presentar|solicitados?)|'
        r'Requisitos?\s+(?:del\s+tr[aá]mite|necesarios?|a\s+presentar)?)',
        text, re.IGNORECASE,
    )

    bloque_text = text[inicio.start():] if inicio else text
    fin = FIN_RE.search(bloque_text)
    if fin:
        bloque_text = bloque_text[:fin.start()]

    KEYWORDS = [
        "identificaci", "comprobante", "solicitud", "formato", "acta",
        "escritura", "contrato", "poder", "curp", "rfc", "predial",
        "fotografía", "croquis", "copia", "original", "licencia",
        "dictamen", "visto bueno", "pago", "constancia", "certificado",
        "permiso", "registro", "titular", "representante", "domicilio",
        "carta", "notarial", "inscripción", "vigente", "oficial",
        "plano", "memoria", "póliza", "seguro", "recibo",
    ]
    META = [
        r'^Presentaci[oó]n:?$', r'^Copias$', r'^Original$',
        r'^Original y copias$', r'^Copias requeridas$', r'^\d+$',
        r'^(Presencial|En l[ií]nea|Ambas)$',
        r'^(?:Hoja\s+Informativa|Fundamento\s+Jur[ií]dico|Iniciar\s+Tr[aá]mite|'
        r'Evaluar\s+Tr[aá]mite|Procedimiento|Protesta\s+ciudadana|'
        r'Tr[aá]mites\s+y\s+servicios|Criterios\s+de\s+resoluci[oó]n|'
        r'Expandir/Contraer|Ver\s+m[aá]s|Ocultar)$',
        r'^Art[ií]culo\s+\d+', r'^\d+\s+fracci[oó]n',
        r'^\d+\.\s+(?:Documentos?\s+de|Comprobantes?\s+de|Documentaci[oó]n)',
        r'^Pago\s+de\s+impuestos\b',
        r'^Peri[oó]dico\s+Oficial\b',
        r'^Ventanilla\s+[Úú]nica\b',
        r'^Solicitudes?\s+de\s+Informaci[oó]n\s+\(',
        r'^(?:Plan\s+(?:Estatal|Municipal)\s+de|Busca\s+en\s+el\s+)',
        r'^Tr[aá]mite\s+de\s+actas\s*:',
        r'^Significado\s+de\s+columnas',
        r'^\¿(?:Hay\s+alg[uú]n\s+error|Encontraste\s+un)',
        r'^(?:Evaluar|Calificar)\s+(?:informaci[oó]n|este\s+tr[aá]mite)',
        r'^(?:Inicio|Noticias|Avisos|Transparencia)\s*[:\-–]\s*\S',
    ]
    SECTION_HEADER = re.compile(
        r'^\d+[\.\)]\s+(?:Documentos?\s+de|Comprobantes?\s+de|Documentaci[oó]n|'
        r'Informaci[oó]n\s+de|Datos\s+de|En\s+caso\s+de)',
        re.IGNORECASE,
    )

    lines = [l.strip() for l in bloque_text.splitlines() if l.strip()]
    i     = 0
    seen  = set()
    while i < len(lines):
        line       = lines[i]
        line_lower = line.lower()
        if any(re.match(p, line, re.IGNORECASE) for p in META) or len(line) < 12 or len(line) > 400:
            i += 1
            continue
        if any(kw in line_lower for kw in KEYWORDS):
            desc   = ""
            pres   = ""
            copias = None
            j      = i + 1
            while j < len(lines) and j < i + 6:
                nl = lines[j].strip()
                if re.match(r'^Presentaci[oó]n', nl, re.IGNORECASE):
                    if j + 1 < len(lines):
                        pres = lines[j + 1].strip()
                elif re.match(r'^Copias requeridas', nl, re.IGNORECASE):
                    if j + 1 < len(lines) and lines[j + 1].strip().isdigit():
                        copias = int(lines[j + 1].strip())
                elif not desc and len(nl) > 15 and not any(re.match(p, nl, re.IGNORECASE) for p in META) and nl != line:
                    desc = nl
                j += 1
            is_header = SECTION_HEADER.match(line)
            texto = line if is_header or not desc or desc.lower() in line.lower() else f"{line}: {desc}"
            key   = texto[:80].lower()
            if key not in seen:
                seen.add(key)
                obl  = not any(w in line_lower for w in ["en su caso", "si aplica", "podrían", "opcional", "cuando aplique", "de ser necesario"])
                cond = re.sub(r'\s+', ' ', line).strip() if not obl else None
                requisitos.append({
                    "texto":        texto,
                    "presentacion": pres or None,
                    "num_copias":   copias,
                    "obligatorio":  obl,
                    "condicion":    cond,
                })
        i += 1

    return _dedup(requisitos)[:40]

def extraer_ubicaciones(text: str) -> list[dict]:
    bloque_m = re.search(r'(Ubicaci[oó]n|D[oó]nde|Lugar[es]* de atenci[oó]n|Unidad administrativa).+', text, re.IGNORECASE | re.DOTALL)
    bloque   = bloque_m.group(0) if bloque_m else text
    dir_     = _re(r'Direcci[oó]n[:\s]+([^\n]{5,150})', bloque)
    if not dir_:
        return []
    nombre_m = re.search(r'([^\n]{5,80})\nDirecci[oó]n', bloque)
    nombre   = re.sub(r'^(Unidad administrativa responsable[^\n]*\n?)', '', nombre_m.group(1).strip() if nombre_m else "", flags=re.IGNORECASE).strip()
    tel_raw  = _re(r'Tel[eé]fono[s]?\(?[s]?\)?[:\s)]+([^\n]{3,80})', bloque)
    tel      = re.sub(r'^[s):\s]+', '', tel_raw).strip() if tel_raw else None
    hora     = _re(r'Horarios?[:\s]+([^\n]{3,40})', bloque)
    dias_raw = _re(r'D[ií]as de atenci[oó]n[:\s]+([^\n]{3,80})', bloque) or _re(r'D[ií]as[:\s]+([^\n]{3,60})', bloque)
    dias     = "Lunes a Viernes" if dias_raw and re.search(r'Lunes.+Viernes', dias_raw) else dias_raw
    return [{"nombre": nombre, "direccion": dir_, "telefono": tel, "horario": hora, "dias": dias}]

def parsear(html: str, fuente: Fuente) -> dict:
    if fuente.parser == "pdf":
        return {
            "doc_tipo": fuente.doc_tipo, "url_fuente": fuente.url,
            "raw_text": None, "requisitos": [], "ubicaciones": [],
            "nombre_tramite": None, "descripcion": "Fuente PDF — requiere extracción manual",
        }
    soup      = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(string=re.compile(r'Expandir/Contraer', re.IGNORECASE)):
        tag.replace_with("")
    for nav_tag in soup.find_all(["nav", "aside"]):
        nav_tag.decompose()
    contenido = None
    for sel in fuente.selector.split(","):
        contenido = soup.select_one(sel.strip())
        if contenido:
            break
    if not contenido:
        contenido = soup.body or soup
    import unicodedata
    text              = contenido.get_text("\n", strip=True)
    text              = unicodedata.normalize("NFC", text)
    text              = re.sub(r'\bExpandir/Contraer\b', '', text, flags=re.IGNORECASE)
    campos            = extraer_campos(text)
    campos["doc_tipo"]   = fuente.doc_tipo
    campos["url_fuente"] = fuente.url
    campos["raw_text"]   = text

    if not campos.get("nombre_tramite"):
        for tag in ["h1", "h2"]:
            el = contenido.find(tag) or soup.find(tag)
            if el:
                t = el.get_text(strip=True)
                if len(t) > 5:
                    campos["nombre_tramite"] = t[:200]
                    break
        if not campos.get("nombre_tramite") and soup.title:
            campos["nombre_tramite"] = (soup.title.string or "").strip()[:200] or None

    campos["requisitos"] = extraer_requisitos(contenido, text)
    campos["ubicaciones"]= extraer_ubicaciones(text)
    return campos


CSV_FIELDS = [
    "estado", "municipio", "tiendas", "doc_tipo", "nombre_tramite", "homoclave",
    "descripcion", "dependencia", "vigencia", "costo", "tiempo_respuesta",
    "requisitos_n", "requisitos_texto", "url_fuente",
]


def append_csv(writer, fuente: Fuente, data: dict) -> None:
    reqs = data.get("requisitos", [])
    writer.writerow({
        "estado":           fuente.estado,
        "municipio":        fuente.municipio,
        "tiendas":          ", ".join(fuente.tiendas),
        "doc_tipo":         fuente.doc_tipo,
        "nombre_tramite":   data.get("nombre_tramite") or "",
        "homoclave":        data.get("homoclave") or "",
        "descripcion":      (data.get("descripcion") or "")[:300],
        "dependencia":      data.get("dependencia") or "",
        "vigencia":         data.get("vigencia") or "",
        "costo":            (data.get("costo") or "")[:200],
        "tiempo_respuesta": data.get("tiempo_respuesta") or "",
        "requisitos_n":     len(reqs),
        "requisitos_texto": " | ".join(r["texto"] for r in reqs)[:1000],
        "url_fuente":       fuente.url,
    })


def procesar(fuente: Fuente, sb: Client, session: requests.Session, writer=None):
    log.info(f"\n{'─'*60}")
    log.info(f"  [{fuente.estado}] {fuente.municipio} — {fuente.doc_tipo}")
    log.info(f"  {fuente.url}")
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    html = fetch(fuente, session)
    if not html:
        msg = "No se pudo obtener HTML"
        log.error(f"  ✗ {msg}")
        log_error_db(sb, fuente, msg)
        return
    try:
        data = parsear(html, fuente)
    except Exception as e:
        msg = f"Error al parsear: {e}"
        log.error(f"  ✗ {msg}")
        log_error_db(sb, fuente, msg)
        return
    if writer:
        append_csv(writer, fuente, data)
    try:
        eid   = upsert_estado(sb, fuente.estado)
        mid   = upsert_municipio(sb, eid, fuente.municipio)
        tid   = insert_tramite(sb, mid, data)
        insert_requisitos(sb, tid, data.get("requisitos", []))
        insert_ubicaciones(sb, tid, data.get("ubicaciones", []))
        n_req = len(data.get("requisitos", []))
        log.info(f"  ✓ tramite_id={tid} | {n_req} requisitos | nombre='{(data.get('nombre_tramite') or '')[:50]}'")
        if n_req == 0:
            log_error_db(sb, fuente, "0 requisitos extraídos — revisar selector o estructura HTML")
    except Exception as e:
        msg = f"Error Supabase: {e}"
        log.error(f"  ✗ {msg}")
        log_error_db(sb, fuente, msg)


def run(fuentes: list[Fuente], filtro_estado=None, filtro_doc=None, out_csv: str = "tramites.csv"):
    sb      = get_supabase()
    session = requests.Session()
    session.headers.update(HEADERS)
    if filtro_estado:
        fuentes = [f for f in fuentes if filtro_estado.lower() in f.estado.lower()]
    if filtro_doc:
        fuentes = [f for f in fuentes if filtro_doc.lower() in f.doc_tipo.lower()]
    log.info(f"\n{'='*60}")
    log.info(f"  gestoria_tramites_legales — {len(fuentes)} fuentes")
    log.info(f"  Supabase: {os.getenv('SUPABASE_URL', 'no configurado')}")
    log.info(f"{'='*60}")
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for i, f in enumerate(fuentes, 1):
            log.info(f"\n[{i}/{len(fuentes)}]")
            procesar(f, sb, session, writer=writer)
            fh.flush()
    log.info(f"\n✅ CSV guardado en: {out_csv}")
    try:
        total = sb.table("tramites").select("id",  count="exact").execute().count
        reqs  = sb.table("requisitos").select("id", count="exact").execute().count
        errs  = sb.table("scraper_errores").select("id", count="exact").eq("reintentado", False).execute().count
        log.info(f"\n{'='*60}")
        log.info(f"  Trámites  : {total}")
        log.info(f"  Requisitos: {reqs}")
        log.info(f"  Errores   : {errs}")
        log.info(f"{'='*60}")
    except Exception:
        pass

def reintenta():
    sb      = get_supabase()
    session = requests.Session()
    rows    = sb.table("scraper_errores").select("*").eq("reintentado", False).execute().data
    log.info(f"Reintentando {len(rows)} errores…")
    for row in rows:
        f = Fuente(estado=row["estado"], municipio=row["municipio"], doc_tipo=row["doc_tipo"], url=row["url"])
        procesar(f, sb, session)
        sb.table("scraper_errores").update({"reintentado": True}).eq("id", row["id"]).execute()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado",    help="Filtrar por estado")
    ap.add_argument("--doc",       help="Filtrar por tipo de documento")
    ap.add_argument("--out",       default="tramites.csv", help="Archivo CSV de salida")
    ap.add_argument("--reintenta", action="store_true")
    ap.add_argument("--listar",    action="store_true")
    args = ap.parse_args()

    if args.listar:
        print(f"\n{'Estado':<22} {'Municipio':<22} {'Tiendas':<18} {'Tipo':<28} Parser")
        print("─" * 100)
        for f in FUENTES:
            print(f"{f.estado:<22} {f.municipio:<22} {', '.join(f.tiendas):<18} {f.doc_tipo:<28} {f.parser}")
        print(f"\nTotal: {len(FUENTES)} fuentes\n")
    elif args.reintenta:
        reintenta()
    else:
        run(FUENTES, filtro_estado=args.estado, filtro_doc=args.doc, out_csv=args.out)
