import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("tiendas.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

DELAY_MIN = 2.0
DELAY_MAX = 5.0
TIMEOUT   = 30
MAX_RETRY = 3

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9",
    "Connection":      "keep-alive",
}

LF = "licencia_funcionamiento"
US = "uso_suelo"
PC = "proteccion_civil"
AN = "anuncio"

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
    tiendas:   list = field(default_factory=list)


FUENTES: list[Fuente] = [
    Fuente("Ciudad de México", "CDMX", US,
           "https://www.cdmx.gob.mx/public/InformacionTramite.xhtml?idTramite=549",
           parser="playwright", tiendas=["T-001", "T-003"]),
    Fuente("Ciudad de México", "CDMX", PC,
           "https://www.cdmx.gob.mx/public/InformacionTramite.xhtml?idTramite=1727",
           parser="playwright", tiendas=["T-001", "T-003"]),
    Fuente("Chiapas", "Tuxtla Gutiérrez", LF,
           "https://tramites.tuxtla.gob.mx/visualizar/241",
           parser="playwright", tiendas=["T-032"]),
    Fuente("Chiapas", "Tuxtla Gutiérrez", US,
           "https://tramites.tuxtla.gob.mx/visualizar/247",
           parser="playwright", tiendas=["T-032"]),
    Fuente("Chiapas", "Tuxtla Gutiérrez", PC,
           "https://proteccioncivil.tuxtla.gob.mx/Dictamen-de-cumplimiento-medidas-de-pc",
           parser="playwright", tiendas=["T-032"]),
    Fuente("Puebla", "Puebla", LF,
           "https://experta.pueblacapital.gob.mx/web/fichaAsunto.do?opcion=0&asas_ide_asu=2470",
           parser="playwright", tiendas=["T-014", "T-016"]),
    Fuente("Puebla", "Puebla", US,
           "https://experta.pueblacapital.gob.mx/web/fichaAsunto.do?opcion=0&asas_ide_asu=184",
           parser="playwright", tiendas=["T-014", "T-016"]),
    Fuente("Puebla", "Puebla", PC,
           "https://experta.pueblacapital.gob.mx/web/fichaAsunto.do?opcion=0&asas_ide_asu=2490",
           parser="playwright", tiendas=["T-014", "T-016"]),
    Fuente("Tabasco", "Villahermosa", LF,
           "https://tramites.villahermosa.gob.mx/tramites/e45fcc3d-7515-4a02-a9c1-0b72ddb3138e",
           parser="playwright", tiendas=["T-034"]),
    Fuente("Tabasco", "Villahermosa", US,
           "https://tramites.villahermosa.gob.mx/tramites/6a36b258-8aa8-486f-a363-63dc033c5665",
           parser="playwright", tiendas=["T-034"]),
    Fuente("Tabasco", "Villahermosa", PC,
           "https://tramites.villahermosa.gob.mx/tramites/b082d02d-9ad8-4c5f-8eeb-fa68e66f372c",
           parser="playwright", tiendas=["T-034"]),
    Fuente("Veracruz", "Veracruz", LF,
           "https://miveracruz.veracruzmunicipio.gob.mx/ver_ficha/uNAZV1LdxmFylzzNHCeL",
           parser="vue", tiendas=["T-022"]),
    Fuente("Veracruz", "Veracruz", US,
           "https://miveracruz.veracruzmunicipio.gob.mx/ver_ficha/d8ea5630-f2c2-11ea-8190-43c3fa7160b6",
           parser="vue", tiendas=["T-022"]),
    Fuente("Veracruz", "Veracruz", PC,
           "https://miveracruz.veracruzmunicipio.gob.mx/ver_ficha/804abe10-e1dd-11ea-8b77-59121d5d03ea",
           parser="vue", tiendas=["T-022"]),
    Fuente("Yucatán", "Mérida", LF,
           "https://isla.merida.gob.mx/serviciosinternet/tramites/detalle/778",
           tiendas=["T-028"]),
    Fuente("Yucatán", "Mérida", US,
           "https://isla.merida.gob.mx/serviciosinternet/tramites/detalle/534",
           tiendas=["T-028"]),
    Fuente("Yucatán", "Mérida", PC,
           "https://isla.merida.gob.mx/serviciosinternet/tramites/detalle/493",
           tiendas=["T-028"]),
    Fuente("Ciudad de México", "CDMX", LF,
           "https://www.cdmx.gob.mx/public/InformacionTramite.xhtml?idTramite=2170",
           parser="playwright", tiendas=["T-001", "T-003"]),
    Fuente("Estado de México", "Chalco", LF,
           "https://gobiernodechalco.gob.mx/tramites-servicios/17-licencia-de-funcionamiento",
           parser="playwright", tiendas=["T-008"]),
    Fuente("Estado de México", "Chalco", PC,
           "https://gobiernodechalco.gob.mx/tramites-servicios/108-dictamen-de-viabilidad",
           parser="playwright", tiendas=["T-008"]),
    Fuente("Ciudad de México", "CDMX", AN,
           "https://www.cdmx.gob.mx/public/InformacionTramite.xhtml?idTramite=2609",
           parser="playwright", tiendas=["T-001", "T-003"]),
    Fuente("Chiapas", "Tuxtla Gutiérrez", AN,
           "https://tramites.tuxtla.gob.mx/visualizar/101",
           parser="playwright", tiendas=["T-032"]),
    Fuente("Puebla", "Puebla", AN,
           "https://experta.pueblacapital.gob.mx/web/fichaAsunto.do?opcion=0&asas_ide_asu=540",
           parser="playwright", tiendas=["T-014", "T-016"]),
    Fuente("Veracruz", "Veracruz", AN,
           "https://miveracruz.veracruzmunicipio.gob.mx/ver_ficha/d3037f40-f164-11ea-88c6-9596a10cbf28",
           parser="vue", tiendas=["T-022"]),
    Fuente("Yucatán", "Mérida", AN,
           "https://isla.merida.gob.mx/serviciosinternet/tramites/detalle/57",
           tiendas=["T-028"]),
    Fuente("Estado de México", "Chalco", AN,
           "https://gobiernodechalco.gob.mx/tramites-servicios/123-permiso-de-publicidad-en-via-publica-anuncios-colgantes-y-mantas",
           parser="playwright", tiendas=["T-008"]),
]


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip() or None


def _text_after(label: str, text: str) -> Optional[str]:
    pat = re.escape(label) + r"[:\s]*\n\s*(.+)"
    m = re.search(pat, text, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).strip()
    return _clean(val[:600]) if val else None


def _dedup(reqs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in reqs:
        key = r["texto"][:80].lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def parse_merida(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    def get_panel(name: str) -> Optional[BeautifulSoup]:
        for h in soup.find_all("div", class_="panel-heading"):
            if name in h.get_text(strip=True):
                return h.find_next_sibling()
        return None

    text = soup.get_text("\n", strip=True)
    homoclave   = _clean(_text_after("Homoclave :", text))
    dependencia = _clean(_text_after("Denominación del área(s) responsables :", text))
    descripcion = _clean(_text_after("Descripción del trámite o servicio:", text))
    tiempo      = _clean(_text_after("Tiempo de resolución del trámite o servicio:", text))
    vigencia    = _clean(_text_after("Vigencia del documento que se obtiene:", text))
    fecha_act   = _clean(_text_after("Fecha de última actualización:", text))

    nombre = None
    for span in soup.find_all("span", class_="titulos"):
        txt = span.get_text(strip=True)
        if txt.startswith("Trámite:") or txt.startswith("Tramite:"):
            nombre = _clean(re.sub(r"^Tr[aá]mite\s*:", "", txt).strip())
            break
    if not nombre:
        nombre_tag = soup.find("h2") or soup.find("h3")
        nombre = _clean(nombre_tag.get_text(strip=True)) if nombre_tag else None

    costo_panel = get_panel("Costos")
    costo_raw = costo_panel.get_text("\n", strip=True) if costo_panel else None
    if costo_raw:
        costo_lines = [l for l in costo_raw.split("\n") if l.strip() and l.strip() != "Costos"]
        costo = _clean(" ".join(costo_lines))
    else:
        costo = None

    req_panel = get_panel("Requisitos")
    reqs = []
    if req_panel:
        ol = req_panel.find("ol")
        if ol:
            for li in ol.find_all("li", recursive=False):
                spans = li.find_all("span", class_="panel-title")
                name_txt = ""
                for sp in spans:
                    if "azul" not in (sp.get("class") or []):
                        name_txt = sp.get_text(strip=True)
                        break
                desc_txt = ""
                pres_txt = ""
                for div in li.find_all("div", recursive=False):
                    label_span = div.find("span", class_=lambda c: c and "azul" in c)
                    if not label_span:
                        continue
                    label_txt = label_span.get_text(strip=True)
                    label_span.extract()
                    val = _clean(div.get_text(" ", strip=True)) or ""
                    if "Descripción" in label_txt:
                        desc_txt = val
                    elif "Presentación" in label_txt or "Tipo de requisito" in label_txt:
                        pres_txt = val
                if name_txt:
                    texto = name_txt + (": " + desc_txt if desc_txt else "")
                    reqs.append({"texto": texto[:600], "presentacion": pres_txt or None, "obligatorio": True})

    data = {
        "doc_tipo":            doc_tipo,
        "nombre_tramite":      nombre,
        "homoclave":           homoclave,
        "descripcion":         descripcion,
        "dependencia":         dependencia,
        "vigencia":            vigencia,
        "costo":               costo,
        "tiempo_respuesta":    tiempo,
        "fecha_actualizacion": fecha_act,
        "url_fuente":          url,
        "raw_text":            text[:5000],
    }
    return data, _dedup(reqs)


def parse_villahermosa(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    def b_value(label: str) -> Optional[str]:
        for b in soup.find_all("b"):
            if label in b.get_text(strip=True):
                parent = b.find_parent()
                val = parent.get_text(" ", strip=True) if parent else ""
                val = val.replace(b.get_text(strip=True), "").strip()
                return _clean(val) or None
        return None

    h3 = soup.find("h3")
    nombre      = _clean(h3.get_text(strip=True)) if h3 else None
    homoclave   = b_value("Homoclave:")
    dependencia = b_value("Unidad administrativa:") or b_value("Subdirección:")
    costo       = b_value("Costo:")
    vigencia    = b_value("Vigencia:")
    tiempo      = b_value("Tiempo de respuesta:") or b_value("Plazo de resolución:")

    descripcion = None
    for p in soup.find_all("p"):
        txt = _clean(p.get_text(strip=True))
        if txt and len(txt) > 20 and ":" not in txt[:15]:
            descripcion = txt
            break

    reqs = []
    for h4 in soup.find_all("h4"):
        if h4.get_text(strip=True) == "Requisitos":
            toggle_div = h4.find_parent("div", class_=re.compile(r"flex|border-b"))
            if toggle_div:
                content_div = toggle_div.find_next_sibling("div")
                if content_div:
                    for li in content_div.find_all("li"):
                        txt = _clean(li.get_text(" ", strip=True))
                        if txt:
                            reqs.append({"texto": txt[:500], "obligatorio": True})
            break

    text = soup.get_text("\n", strip=True)
    data = {
        "doc_tipo":         doc_tipo,
        "nombre_tramite":   nombre,
        "homoclave":        homoclave,
        "descripcion":      descripcion,
        "dependencia":      dependencia,
        "vigencia":         vigencia,
        "costo":            costo,
        "tiempo_respuesta": tiempo,
        "url_fuente":       url,
        "raw_text":         text[:5000],
    }
    return data, _dedup(reqs)


def parse_tuxtla(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    text = soup.get_text("\n", strip=True)
    contenedor: dict = {}
    for script in soup.find_all("script"):
        src = script.get_text()
        m = re.search(r"modalidades_json\s*=\s*(\{.+?\});\s*\n", src, re.DOTALL)
        if m:
            try:
                jdata = json.loads(m.group(1))
                contenedor = jdata.get("0", {}).get("contenedor", {})
            except json.JSONDecodeError:
                pass
            break

    def json_val(key: str) -> Optional[str]:
        block = contenedor.get(key, {})
        for v in block.get("valores", {}).values():
            val = v.get("valor", "")
            if val and val.strip():
                return _clean(val)
        return None

    def json_doc(key: str) -> Optional[str]:
        block = contenedor.get(key, {})
        for v in block.get("valores", {}).values():
            doc = v.get("documento", "")
            if doc and doc.strip():
                return doc.strip()
        return None

    nombre      = _clean(_text_after("Nombre del trámite:", text))
    dependencia = _clean(_text_after("Dependencia responsable:", text)) or \
                  _clean(_text_after("Unidad administrativa del trámite:", text))
    descripcion = _clean(_text_after("Descripción general:", text))
    costo       = json_val("0_10006") or _clean(_text_after("Monto a pagar", text))
    tiempo      = json_val("0_10008") or _clean(_text_after("Tiempo de respuesta", text))
    vigencia    = json_val("0_10013") or _clean(_text_after("Vigencia", text))
    fecha_act   = _clean(_text_after("Ultima modificación:", text))

    reqs = []
    doc_raw = json_doc("0_10005")
    if doc_raw:
        for line in doc_raw.split("\n"):
            line = line.strip()
            if line and len(line) > 5:
                reqs.append({"texto": line[:600], "obligatorio": True})
    else:
        m = re.search(r"Documentos requeridos\s*\nDocumento para entregar:\s*\n(.+?)(?=\nNúmero de originales|\nOrdenamientos|\Z)",
                      text, re.DOTALL)
        if m:
            for line in m.group(1).split("\n"):
                line = line.strip()
                if line and re.match(r'^[a-z]\)', line, re.I):
                    reqs.append({"texto": line[:600], "obligatorio": True})

    data = {
        "doc_tipo":            doc_tipo,
        "nombre_tramite":      nombre,
        "dependencia":         dependencia,
        "descripcion":         descripcion,
        "vigencia":            vigencia,
        "costo":               costo,
        "tiempo_respuesta":    tiempo,
        "fecha_actualizacion": fecha_act,
        "url_fuente":          url,
        "raw_text":            text[:5000],
    }
    return data, _dedup(reqs)


def parse_puebla(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    def get_section(name: str) -> Optional[BeautifulSoup]:
        for h in soup.find_all("div", class_="panel-heading"):
            title_div = h.find("div", class_="panel-title")
            if title_div and name in title_div.get_text(strip=True):
                target_id = h.get("data-target", "").lstrip("#")
                if target_id:
                    return soup.find(id=target_id)
                return h.find_next_sibling(class_=re.compile("panel-collapse"))
        return None

    def section_text(name: str) -> Optional[str]:
        sec = get_section(name)
        return _clean(sec.get_text(" ", strip=True)) if sec else None

    nombre = None
    for h1 in soup.find_all("h1"):
        txt = h1.get_text(strip=True)
        if txt and "Gobierno" not in txt and len(txt) > 5:
            nombre = _clean(txt)
            break
    if not nombre:
        for h3 in soup.find_all("h3"):
            txt = h3.get_text(strip=True)
            if txt and "Cargando" not in txt:
                nombre = _clean(txt)
                break

    descripcion = section_text("Objetivo del trámite")
    dependencia = section_text("Dependencia o Entidad") or section_text("Área responsable")
    tiempo      = section_text("Tiempo de respuesta")
    costo       = section_text("Costo")
    vigencia    = section_text("Vigencia")

    reqs = []
    req_sec = get_section("Requisitos")
    if req_sec:
        table = req_sec.find("table")
        if table:
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    nombre_req = _clean(cols[0].get_text(" ", strip=True)) or ""
                    desc_req   = _clean(cols[1].get_text(" ", strip=True)) or ""
                    pres_req   = _clean(cols[2].get_text(" ", strip=True)) if len(cols) > 2 else None
                    texto = nombre_req + (": " + desc_req if desc_req else "")
                    if texto.strip():
                        reqs.append({"texto": texto[:600], "presentacion": pres_req, "obligatorio": True})
        doc_sec = get_section("Documentación a adjuntar")
        if doc_sec:
            for line in doc_sec.get_text("\n", strip=True).split("\n"):
                line = line.strip()
                if len(line) > 10 and not any(kw in line.lower() for kw in ("en caso de", "documentación básica", "básica")):
                    if not any(r["texto"].startswith(line[:30]) for r in reqs):
                        reqs.append({"texto": line[:500], "obligatorio": True})

    text = soup.get_text("\n", strip=True)
    data = {
        "doc_tipo":         doc_tipo,
        "nombre_tramite":   nombre,
        "descripcion":      descripcion,
        "dependencia":      dependencia,
        "vigencia":         vigencia,
        "costo":            costo,
        "tiempo_respuesta": tiempo,
        "url_fuente":       url,
        "raw_text":         text[:5000],
    }
    return data, _dedup(reqs)


def parse_cdmx(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    def line_after(label: str) -> Optional[str]:
        for i, l in enumerate(lines):
            if l == label and i + 1 < len(lines):
                return _clean(lines[i + 1])
        return None

    nombre = None
    for l in lines[:25]:
        if len(l) > 15 and re.search(r'[A-ZÁÉÍÓÚ]', l) and "CDMX" not in l and "Gobierno" not in l:
            nombre = l
            break

    descripcion = None
    for i, l in enumerate(lines):
        if "¿Quién realiza" in l and i + 1 < len(lines):
            descripcion = _clean(lines[i + 1])
            break
    if not descripcion:
        for i, l in enumerate(lines):
            if len(l) > 60 and not any(kw in l for kw in ("Inicio", "¿", "Este", "Descarga", "Puedes")):
                descripcion = _clean(l)
                break

    costo = None
    for i, l in enumerate(lines):
        if "Monto a pagar" in l:
            amount_parts = [l]
            if i + 1 < len(lines) and lines[i + 1].replace(",", "").replace(".", "").strip().isdigit():
                amount_parts.append(lines[i + 1])
            costo = _clean(" ".join(amount_parts))
            break

    vigencia    = line_after("Vigencia") or line_after("Documento que se obtiene:")
    tiempo      = line_after("Duración / Respuesta")
    dependencia = None
    for l in lines:
        if l.startswith("UNIDAD NORMATIVA:"):
            dependencia = _clean(l.replace("UNIDAD NORMATIVA:", "").strip())
            break

    reqs = []
    in_reqs = False
    current_group = ""
    for l in lines:
        if l == "Requisitos:":
            in_reqs = True
            continue
        if in_reqs:
            if re.match(r"^\d+\.", l):
                current_group = l
                reqs.append({"texto": l[:400], "obligatorio": True})
            elif l and not any(kw in l for kw in ("¿Cómo", "De manera digital", "Descarga", "Costos", "Vigencia", "Duración")):
                texto = (current_group + " — " + l if current_group else l)[:500]
                if len(l) > 8:
                    reqs.append({"texto": texto, "obligatorio": True})
            if "Cómo, dónde" in l or "¿Cómo" in l:
                break

    data = {
        "doc_tipo":         doc_tipo,
        "nombre_tramite":   nombre,
        "descripcion":      descripcion,
        "dependencia":      dependencia,
        "vigencia":         vigencia,
        "costo":            costo,
        "tiempo_respuesta": tiempo,
        "url_fuente":       url,
        "raw_text":         soup.get_text("\n", strip=True)[:5000],
    }
    return data, _dedup(reqs)


def parse_veracruz(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if sum(1 for l in lines[:20] if l == "Loading...") >= 3:
        log.warning("  Veracruz SPA no cargó correctamente")
        return {}, []

    def b_value(label: str) -> Optional[str]:
        for b in soup.find_all("b"):
            if label in b.get_text(strip=True):
                parent = b.find_parent()
                val = parent.get_text(" ", strip=True).replace(b.get_text(strip=True), "").strip()
                return _clean(val) or None
        return None

    homoclave   = b_value("Homoclave:") or b_value("Clave:")
    dependencia = b_value("Unidad administrativa:") or b_value("Área responsable:")
    costo       = b_value("Costo:") or b_value("Derechos:")
    vigencia    = b_value("Vigencia:")
    tiempo      = b_value("Tiempo de respuesta:") or b_value("Plazo:")

    h_tag = soup.find(["h1", "h2", "h3"])
    nombre = _clean(h_tag.get_text(strip=True)) if h_tag else None

    descripcion = None
    for p in soup.find_all("p"):
        txt = _clean(p.get_text(strip=True))
        if txt and len(txt) > 30:
            descripcion = txt
            break

    if not costo:
        costo = _clean(_text_after("Costo", text)) or _clean(_text_after("Derechos", text))
    if not vigencia:
        vigencia = _clean(_text_after("Vigencia", text))
    if not tiempo:
        tiempo = _clean(_text_after("Tiempo de respuesta", text))

    reqs = []
    for h4 in soup.find_all(["h4", "h3", "strong"]):
        if re.search(r"requisito", h4.get_text(strip=True), re.I):
            toggle_div = h4.find_parent("div", class_=re.compile(r"flex|border"))
            if toggle_div:
                content_div = toggle_div.find_next_sibling("div")
                if content_div:
                    for li in content_div.find_all("li"):
                        txt = _clean(li.get_text(" ", strip=True))
                        if txt:
                            reqs.append({"texto": txt[:500], "obligatorio": True})
                    break
    if not reqs:
        for ul in soup.find_all("ul"):
            lis = ul.find_all("li")
            if 3 <= len(lis) <= 25:
                candidate = [_clean(li.get_text(" ", strip=True)) for li in lis]
                if all(c and len(c) > 10 for c in candidate[:3]):
                    reqs = [{"texto": c[:500], "obligatorio": True} for c in candidate if c]
                    break

    data = {
        "doc_tipo":         doc_tipo,
        "nombre_tramite":   nombre,
        "homoclave":        homoclave,
        "descripcion":      descripcion,
        "dependencia":      dependencia,
        "vigencia":         vigencia,
        "costo":            costo,
        "tiempo_respuesta": tiempo,
        "url_fuente":       url,
        "raw_text":         text[:5000],
    }
    return data, _dedup(reqs)


def parse_chalco(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    def after_label(label: str) -> Optional[str]:
        SKIP = {"ORIGINAL:", "COPIAS:", "TRÁMITE:", "SERVICIO:", "NOMBRE:",
                "DESCRIPCIÓN:", "CÓDIGO DE LA CÉDULA:", "FUNDAMENTO LEGAL:"}
        for i, l in enumerate(lines):
            if l == label:
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j] and lines[j] not in SKIP and not lines[j].isupper():
                        return _clean(lines[j])
        return None

    nombre      = after_label("SERVICIO:")
    descripcion = after_label("DESCRIPCIÓN:")
    vigencia    = after_label("VIGENCIA DEL DOCUMENTO A OBTENER:")
    tiempo      = after_label("PLAZO MÁXIMO DE RESPUESTA:")
    costo       = after_label("COSTO:")
    dependencia = after_label("UNIDAD ADMINISTRATIVA RESPONSABLE:")

    REQS_SKIP = {"ORIGINAL:", "COPIAS:", "PERSONAS FÍSICAS", "PERSONAS MORALES", "ALTA", "REVALIDACIÓN", "BAJA"}
    REQS_STOP = {"PLAZO MÁXIMO DE RESPUESTA:", "COSTO:", "FUNDAMENTO LEGAL PARA SU COBRO:",
                 "FORMA DE PAGO:", "APLICACIÓN DE LA AFIRMATIVA FICTA?",
                 "DEPENDENCIA U ORGANISMO:", "TRÁMITES O SERVICIOS RELACIONADOS:"}
    reqs = []
    in_reqs = False
    for l in lines:
        if l == "REQUISITOS:":
            in_reqs = True
            continue
        if in_reqs:
            if l in REQS_STOP:
                break
            if l in REQS_SKIP or (l.isupper() and not re.match(r"^\d+", l)):
                continue
            if re.match(r"^\d+[\.\)]\s+\S", l) and len(l) > 8:
                reqs.append({"texto": _clean(l)[:500], "obligatorio": True})

    data = {
        "doc_tipo":         doc_tipo,
        "nombre_tramite":   nombre,
        "descripcion":      descripcion,
        "dependencia":      dependencia,
        "vigencia":         vigencia,
        "costo":            costo,
        "tiempo_respuesta": tiempo,
        "url_fuente":       url,
        "raw_text":         text[:5000],
    }
    return data, _dedup(reqs)


def parse_generic(soup: BeautifulSoup, url: str, doc_tipo: str) -> tuple[dict, list]:
    text = soup.get_text("\n", strip=True)

    def re_find(pattern):
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return _clean(m.group(1)) if m else None

    nombre      = re_find(r"(?:Nombre del tr[aá]mite|Denominaci[oó]n)[:\s]*\n(.+)")
    descripcion = re_find(r"(?:Descripci[oó]n|Objetivo)[:\s]*\n(.+?)(?=\n\S+:|\Z)")
    dependencia = re_find(r"(?:Dependencia|[Áá]rea responsable|Unidad administrativa)[:\s]*\n(.+)")
    tiempo      = re_find(r"Tiempo de respuesta[:\s]*\n(.+)")
    vigencia    = re_find(r"Vigencia[:\s]*\n(.+)")
    costo       = re_find(r"(?:Costo|Monto|Derechos)[:\s]*\n(.+)")

    reqs = []
    for li in soup.find_all("li"):
        txt = _clean(li.get_text(" ", strip=True))
        if txt and 8 < len(txt) < 600:
            reqs.append({"texto": txt, "obligatorio": True})

    data = {
        "doc_tipo":         doc_tipo,
        "nombre_tramite":   nombre,
        "descripcion":      descripcion,
        "dependencia":      dependencia,
        "vigencia":         vigencia,
        "costo":            costo,
        "tiempo_respuesta": tiempo,
        "url_fuente":       url,
        "raw_text":         text[:5000],
    }
    return data, _dedup(reqs)


DOMAIN_PARSERS = {
    "isla.merida.gob.mx":                     parse_merida,
    "tramites.villahermosa.gob.mx":           parse_villahermosa,
    "tramites.tuxtla.gob.mx":                 parse_tuxtla,
    "experta.pueblacapital.gob.mx":           parse_puebla,
    "www.cdmx.gob.mx":                        parse_cdmx,
    "cdmx.gob.mx":                            parse_cdmx,
    "proteccioncivil.cdmx.gob.mx":            parse_cdmx,
    "proteccioncivil.tuxtla.gob.mx":          parse_generic,
    "miveracruz.veracruzmunicipio.gob.mx":    parse_veracruz,
    "gobiernodechalco.gob.mx":                parse_chalco,
}


def fetch_requests(url: str, session: requests.Session) -> Optional[str]:
    import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for i in range(1, MAX_RETRY + 1):
        try:
            r = session.get(url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True, verify=False)
            if r.status_code == 200:
                return r.text
            log.warning(f"  HTTP {r.status_code} (intento {i})")
        except requests.RequestException as e:
            log.warning(f"  {e} (intento {i})")
        time.sleep(2 ** i)
    return None


def fetch_playwright(url: str, wait_ms: int = 4000, wait_selector: Optional[str] = None,
                     wait_networkidle: bool = False) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="es-MX",
                viewport={"width": 1280, "height": 900},
            ).new_page()
            wait_until = "networkidle" if wait_networkidle else "domcontentloaded"
            page.goto(url, wait_until=wait_until, timeout=60_000)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=15_000)
                except Exception:
                    pass
            page.wait_for_timeout(wait_ms)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.error(f"  Playwright: {e}")
        return None


def fetch(fuente: Fuente, session: requests.Session) -> Optional[str]:
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    domain = urlparse(fuente.url).netloc

    if fuente.parser == "vue":
        log.info(f"  → Vue SPA fetch (networkidle)")
        return fetch_playwright(fuente.url, wait_ms=8000, wait_networkidle=True)

    if fuente.parser == "playwright":
        wait_selector = None
        if "merida" in domain:
            wait_selector = ".panel-body"
        elif "villahermosa" in domain:
            wait_selector = "h4"
        elif "tuxtla.gob.mx" in domain and "proteccion" not in domain:
            wait_selector = "script"
        elif "pueblacapital" in domain:
            wait_selector = ".panel-heading"
        elif "cdmx.gob.mx" in domain:
            wait_selector = "#contenidoForm, .tramite-container, main"
        return fetch_playwright(fuente.url, wait_ms=3000, wait_selector=wait_selector)

    html = fetch_requests(fuente.url, session)
    if not html:
        return fetch_playwright(fuente.url, wait_ms=3000)
    soup_preview = BeautifulSoup(html, "lxml")
    if len(soup_preview.get_text(strip=True)) < 300:
        log.info("  HTML escaso, reintentando con Playwright…")
        return fetch_playwright(fuente.url, wait_ms=3000)
    return html


def get_supabase() -> Optional[Client]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        log.warning("SUPABASE_URL / SUPABASE_KEY no configurados — sin persistencia en BD")
        return None
    return create_client(url, key)


def upsert_estado(sb, nombre: str) -> int:
    sb.table("estados").upsert({"nombre": nombre}, on_conflict="nombre").execute()
    return sb.table("estados").select("id").eq("nombre", nombre).single().execute().data["id"]


def upsert_municipio(sb, estado_id: int, nombre: str) -> int:
    sb.table("municipios").upsert({"estado_id": estado_id, "nombre": nombre},
                                   on_conflict="estado_id,nombre").execute()
    return (sb.table("municipios").select("id")
              .eq("estado_id", estado_id).eq("nombre", nombre).single().execute().data["id"])


def insert_tramite(sb, municipio_id: int, data: dict) -> int:
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


def insert_requisitos(sb, tramite_id: int, reqs: list[dict]) -> None:
    if not reqs:
        return
    rows = [{
        "tramite_id":  tramite_id,
        "orden":       i + 1,
        "texto":       r["texto"],
        "presentacion":r.get("presentacion"),
        "num_copias":  r.get("num_copias"),
        "obligatorio": r.get("obligatorio", True),
        "condicion":   r.get("condicion"),
    } for i, r in enumerate(reqs)]
    sb.table("requisitos").insert(rows).execute()


CSV_FIELDS = [
    "estado", "municipio", "tiendas", "doc_tipo", "nombre_tramite", "homoclave",
    "descripcion", "dependencia", "vigencia", "costo", "tiempo_respuesta",
    "requisitos_n", "requisitos_texto", "url_fuente",
]


def append_csv(writer, fuente: Fuente, data: dict, reqs: list[dict]) -> None:
    writer.writerow({
        "estado":           fuente.estado,
        "municipio":        fuente.municipio,
        "tiendas":          ", ".join(fuente.tiendas),
        "doc_tipo":         fuente.doc_tipo,
        "nombre_tramite":   data.get("nombre_tramite", ""),
        "homoclave":        data.get("homoclave", ""),
        "descripcion":      (data.get("descripcion") or "")[:300],
        "dependencia":      data.get("dependencia", ""),
        "vigencia":         data.get("vigencia", ""),
        "costo":            (data.get("costo") or "")[:300],
        "tiempo_respuesta": data.get("tiempo_respuesta", ""),
        "requisitos_n":     len(reqs),
        "requisitos_texto": " | ".join(r["texto"] for r in reqs)[:1000],
        "url_fuente":       fuente.url,
    })


def main() -> None:
    ap = argparse.ArgumentParser(description="Scraper especializado Tiendas 21")
    ap.add_argument("--debug",  action="store_true", help="Guardar HTML en /tmp/tiendas_debug/")
    ap.add_argument("--no-db",  action="store_true", help="No insertar en Supabase")
    ap.add_argument("--only",   nargs="+", metavar="MUNICIPIO", help="Scrape solo estos municipios")
    ap.add_argument("--out",    default="tiendas_tramites.csv", help="Archivo CSV de salida")
    args = ap.parse_args()

    if args.debug:
        os.makedirs("/tmp/tiendas_debug", exist_ok=True)

    sb = None if args.no_db else get_supabase()
    session = requests.Session()

    fuentes = FUENTES
    if args.only:
        fuentes = [f for f in FUENTES if f.municipio in args.only]
        log.info(f"Filtrando a {len(fuentes)} fuentes para: {args.only}")

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for fuente in fuentes:
            log.info(f"▶ {fuente.estado} / {fuente.municipio} / {fuente.doc_tipo}")
            log.info(f"  URL: {fuente.url}")

            html = fetch(fuente, session)
            if not html:
                log.error(f"  ✗ Sin HTML — saltando")
                continue

            if args.debug:
                fname = f"{fuente.municipio.replace(' ','_')}_{fuente.doc_tipo}.html"
                with open(f"/tmp/tiendas_debug/{fname}", "w", encoding="utf-8") as f:
                    f.write(html)

            soup = BeautifulSoup(html, "lxml")
            domain = urlparse(fuente.url).netloc
            parser_fn = DOMAIN_PARSERS.get(domain, parse_generic)
            log.info(f"  Parser: {parser_fn.__name__}")

            try:
                data, reqs = parser_fn(soup, fuente.url, fuente.doc_tipo)
            except Exception as e:
                log.error(f"  ✗ Parse error: {e}", exc_info=True)
                continue

            if not data:
                log.warning(f"  ✗ Parser devolvió datos vacíos")
                continue

            log.info(f"  ✓ nombre={data.get('nombre_tramite','?')!r} | reqs={len(reqs)} | costo={data.get('costo','?')!r}")

            append_csv(writer, fuente, data, reqs)
            fh.flush()

            if sb:
                try:
                    estado_id    = upsert_estado(sb, fuente.estado)
                    municipio_id = upsert_municipio(sb, estado_id, fuente.municipio)
                    tramite_id   = insert_tramite(sb, municipio_id, data)
                    insert_requisitos(sb, tramite_id, reqs)
                    log.info(f"  ✓ DB tramite_id={tramite_id}")
                except Exception as e:
                    log.error(f"  ✗ DB error: {e}", exc_info=True)

    log.info(f"\n✅ CSV guardado en: {args.out}")


if __name__ == "__main__":
    main()
