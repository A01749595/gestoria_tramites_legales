"""
Tramites Service — gestión de los trámites de vigencia capturados
manualmente por sucursal.

Persistencia: un archivo JSON en disco (tramites_data.json). La primera
vez que se arranca, si el JSON no existe, se precarga con los datos
semilla extraídos de TRAMITES.docx (config/tramites_seed.py).

Estructura del JSON:
{
  "sucursales": [
    {
      "tramite_id": "T-001",
      "nombre": "San Antonio Abad",
      "estado": "",            # opcional, lo llena el usuario
      "municipio": "",         # opcional
      "permisos": [
        {"no": "1", "permiso": "Aviso de funcionamiento",
         "vigencia_2025": "Permanente", "vigencia_2026": "Permanente"},
        ...
      ]
    },
    ...
  ],
  "actualizado_en": "2026-..."
}

El % de cumplimiento por sucursal se calcula SOLO sobre los 5 trámites
requeridos (TRAMITES_REQUERIDOS), evaluando la columna de vigencia 2026
(el año prioritario del proyecto).
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date
import json
import os
import re
import logging
import unicodedata

logger = logging.getLogger(__name__)

# Ruta del JSON de persistencia. Se puede mover con la env TRAMITES_DATA_FILE.
DATA_FILE = os.getenv(
    "TRAMITES_DATA_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tramites_data.json"),
)


# ──────────────────────────────────────────────────────────────────────
# Normalización del estado de un permiso
# ──────────────────────────────────────────────────────────────────────
def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(c) != "Mn"
    )


# Valores textuales que NO son fechas pero indican un estado concreto.
# Se comparan sin acentos y en minúsculas.
_TEXT_STATES = {
    "permanente": "vigente",       # no vence nunca -> cuenta como vigente
    "pagado": "vigente",           # ya se pagó la renovación -> vigente
    "vo bo": "vigente",            # visto bueno otorgado
    "visto bueno": "vigente",
    "ingreso": "en_tramite",       # documento ingresado, en proceso
    "ingresado": "en_tramite",
    "pendiente": "en_tramite",     # trámite iniciado pero sin resolver
    "en tramite": "en_tramite",
    "no aplica": "no_aplica",      # ese permiso no aplica a la sucursal
    "sin tramite": "sin_tramite",  # no se ha podido iniciar
    "sin tramitar": "sin_tramite",
}


def clasificar_vigencia(valor: str) -> Dict[str, Any]:
    """
    Clasifica el valor de una celda de vigencia.

    Devuelve dict con:
      estado: uno de 'vigente' | 'por_vencer' | 'vencido' | 'en_tramite'
              | 'no_aplica' | 'sin_tramite' | 'sin_dato'
      fecha:  date si el valor era una fecha parseable, si no None
      cuenta_para_porcentaje: bool — si este permiso debe contar en el
              denominador del % (no_aplica NO cuenta).
      cumple: bool — si cuenta como "cumplido" para el % .
    """
    raw = (valor or "").strip()
    if not raw:
        return {"estado": "sin_dato", "fecha": None,
                "cuenta_para_porcentaje": True, "cumple": False}

    # ¿Es un estado textual conocido?
    key = _strip_accents(raw).lower()
    if key in _TEXT_STATES:
        estado = _TEXT_STATES[key]
        if estado == "no_aplica":
            return {"estado": "no_aplica", "fecha": None,
                    "cuenta_para_porcentaje": False, "cumple": False}
        if estado == "vigente":
            return {"estado": "vigente", "fecha": None,
                    "cuenta_para_porcentaje": True, "cumple": True}
        if estado == "en_tramite":
            # En trámite cuenta como medio cumplido (ver porcentaje abajo).
            return {"estado": "en_tramite", "fecha": None,
                    "cuenta_para_porcentaje": True, "cumple": False}
        # sin_tramite
        return {"estado": "sin_tramite", "fecha": None,
                "cuenta_para_porcentaje": True, "cumple": False}

    # ¿Es una fecha dd/mm/yyyy o ISO?
    fecha = _parse_fecha(raw)
    if fecha is not None:
        hoy = date.today()
        dias = (fecha - hoy).days
        if dias < 0:
            estado = "vencido"
        elif dias <= 45:
            estado = "por_vencer"
        else:
            estado = "vigente"
        return {"estado": estado, "fecha": fecha,
                "cuenta_para_porcentaje": True, "cumple": estado != "vencido"}

    # Texto no reconocido: lo tratamos como sin dato útil.
    return {"estado": "sin_dato", "fecha": None,
            "cuenta_para_porcentaje": True, "cumple": False}


def _parse_fecha(valor: str) -> Optional[date]:
    """Intenta parsear dd/mm/yyyy, dd-mm-yyyy o ISO. None si no se puede."""
    valor = (valor or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            continue
    return None


# Etiquetas legibles para el frontend.
ESTADO_LABEL = {
    "vigente": "Vigente",
    "por_vencer": "Por vencer",
    "vencido": "Vencido",
    "en_tramite": "En trámite",
    "no_aplica": "No aplica",
    "sin_tramite": "Sin trámite",
    "sin_dato": "Sin información",
}


# ──────────────────────────────────────────────────────────────────────
# Cálculo del % de cumplimiento por sucursal
# ──────────────────────────────────────────────────────────────────────
def calcular_cumplimiento(sucursal: Dict[str, Any], requeridos: List[str]) -> Dict[str, Any]:
    """
    Calcula el % de cumplimiento de UNA sucursal sobre los trámites
    requeridos, evaluando la vigencia 2026.

    Reglas de puntaje (sobre cada trámite requerido):
      - vigente               -> 1.0 punto
      - en_tramite / por_vencer -> 0.5 puntos
      - vencido / sin_tramite / sin_dato -> 0 puntos
      - no_aplica             -> el trámite se excluye del denominador

    % = (suma de puntos / # de trámites que sí aplican) * 100
    """
    permisos = sucursal.get("permisos", [])
    # Indexamos los permisos por nombre normalizado para buscar los requeridos.
    by_name = {}
    for p in permisos:
        by_name[_norm_permiso(p.get("permiso", ""))] = p

    puntos = 0.0
    denominador = 0
    detalle = []
    for req in requeridos:
        p = by_name.get(_norm_permiso(req))
        valor_2026 = (p or {}).get("vigencia_2026", "") if p else ""
        cls = clasificar_vigencia(valor_2026)
        if not cls["cuenta_para_porcentaje"]:
            # no_aplica: no suma al denominador
            detalle.append({"tramite": req, "estado": cls["estado"],
                            "valor": valor_2026, "puntos": None})
            continue
        denominador += 1
        if cls["estado"] == "vigente":
            pts = 1.0
        elif cls["estado"] in ("en_tramite", "por_vencer"):
            pts = 0.5
        else:
            pts = 0.0
        puntos += pts
        detalle.append({"tramite": req, "estado": cls["estado"],
                        "valor": valor_2026, "puntos": pts})

    porcentaje = round((puntos / denominador) * 100, 1) if denominador > 0 else 0.0
    return {
        "porcentaje": porcentaje,
        "puntos": puntos,
        "denominador": denominador,
        "detalle": detalle,
        "completo": porcentaje >= 100.0,
    }


def _norm_permiso(nombre: str) -> str:
    """Normaliza el nombre de un permiso para comparar (sin acentos, minúsculas)."""
    n = _strip_accents(nombre or "").lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    # "proteccion civil visto bueno" y "proteccion civil" se consideran iguales.
    n = n.replace("proteccion civil visto bueno", "proteccion civil")
    return n


# ──────────────────────────────────────────────────────────────────────
# Servicio (carga / guarda / consulta)
# ──────────────────────────────────────────────────────────────────────
class TramitesService:
    def __init__(self, data_file: str = DATA_FILE):
        self.data_file = data_file
        # Importamos la semilla aquí para no crear dependencia circular.
        try:
            from config.tramites_seed import TRAMITES_SEED, TRAMITES_REQUERIDOS
            self._seed = TRAMITES_SEED
            self.requeridos = TRAMITES_REQUERIDOS
        except Exception as e:
            logger.error("No se pudo importar tramites_seed: %s", e)
            self._seed = []
            self.requeridos = [
                "Aviso de funcionamiento", "Uso de suelo", "Anuncio",
                "Protección Civil Visto Bueno", "Licencia Ambiental",
            ]
        self._ensure_file()

    def _ensure_file(self):
        """Crea el JSON con datos semilla si todavía no existe."""
        if not os.path.exists(self.data_file):
            payload = {
                "sucursales": [self._normalize_sucursal(s) for s in self._seed],
                "actualizado_en": datetime.now().isoformat(),
            }
            self._write(payload)
            logger.info("tramites_data.json creado con %d sucursales semilla", len(self._seed))

    @staticmethod
    def _normalize_sucursal(s: Dict[str, Any]) -> Dict[str, Any]:
        """Asegura que la sucursal tenga todos los campos esperados."""
        return {
            "tramite_id": s.get("tramite_id", ""),
            "nombre": s.get("nombre", ""),
            "estado": s.get("estado", ""),
            "municipio": s.get("municipio", ""),
            "permisos": [
                {
                    "no": str(p.get("no", "")),
                    "permiso": p.get("permiso", ""),
                    "vigencia_2025": p.get("vigencia_2025", ""),
                    "vigencia_2026": p.get("vigencia_2026", ""),
                }
                for p in s.get("permisos", [])
            ],
        }

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Error leyendo tramites_data.json: %s", e)
            return {"sucursales": [], "actualizado_en": None}

    def _write(self, payload: Dict[str, Any]):
        tmp = self.data_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.data_file)  # escritura atómica

    # --- API pública ---

    def get_all(self) -> Dict[str, Any]:
        """Devuelve todas las sucursales con su % de cumplimiento calculado."""
        data = self._read()
        sucursales = []
        for s in data.get("sucursales", []):
            s_norm = self._normalize_sucursal(s)
            cumpl = calcular_cumplimiento(s_norm, self.requeridos)
            sucursales.append({**s_norm, "cumplimiento": cumpl})
        return {
            "sucursales": sucursales,
            "tramites_requeridos": self.requeridos,
            "actualizado_en": data.get("actualizado_en"),
            "total_sucursales": len(sucursales),
        }

    def save_sucursal(self, sucursal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserta o actualiza UNA sucursal (match por tramite_id).
        Devuelve la sucursal guardada con su % recalculado.
        """
        data = self._read()
        s_norm = self._normalize_sucursal(sucursal)
        lista = data.get("sucursales", [])
        idx = next((i for i, x in enumerate(lista)
                    if x.get("tramite_id") == s_norm["tramite_id"]), None)
        if idx is not None:
            lista[idx] = s_norm
        else:
            lista.append(s_norm)
        data["sucursales"] = lista
        data["actualizado_en"] = datetime.now().isoformat()
        self._write(data)
        cumpl = calcular_cumplimiento(s_norm, self.requeridos)
        return {**s_norm, "cumplimiento": cumpl}

    def delete_sucursal(self, tramite_id: str) -> bool:
        data = self._read()
        lista = data.get("sucursales", [])
        nueva = [x for x in lista if x.get("tramite_id") != tramite_id]
        if len(nueva) == len(lista):
            return False
        data["sucursales"] = nueva
        data["actualizado_en"] = datetime.now().isoformat()
        self._write(data)
        return True

    def reset_to_seed(self) -> Dict[str, Any]:
        """Restaura el JSON a los datos semilla del TRAMITES.docx."""
        payload = {
            "sucursales": [self._normalize_sucursal(s) for s in self._seed],
            "actualizado_en": datetime.now().isoformat(),
        }
        self._write(payload)
        return self.get_all()

    def resumen_por_sucursal(self) -> List[Dict[str, Any]]:
        """
        Devuelve una lista compacta para el dashboard:
        [{tramite_id, nombre, estado, municipio, porcentaje, completo,
          vigentes, por_vencer, vencidos, ...}]
        """
        out = []
        for s in self.get_all()["sucursales"]:
            cumpl = s["cumplimiento"]
            # Contamos estados de los 5 requeridos
            counts = {"vigente": 0, "por_vencer": 0, "vencido": 0,
                      "en_tramite": 0, "no_aplica": 0, "sin_tramite": 0,
                      "sin_dato": 0}
            for d in cumpl["detalle"]:
                counts[d["estado"]] = counts.get(d["estado"], 0) + 1
            out.append({
                "tramite_id": s["tramite_id"],
                "nombre": s["nombre"],
                "estado": s.get("estado", ""),
                "municipio": s.get("municipio", ""),
                "porcentaje": cumpl["porcentaje"],
                "completo": cumpl["completo"],
                "vigentes": counts["vigente"],
                "por_vencer": counts["por_vencer"] + counts["en_tramite"],
                "vencidos": counts["vencido"],
                "sin_tramite": counts["sin_tramite"] + counts["sin_dato"],
                "no_aplica": counts["no_aplica"],
            })
        return out
