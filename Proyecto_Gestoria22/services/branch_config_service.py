"""
Branch Config Service — configuración de correos por sucursal.

Persiste en branch_config.json los correos asignados individualmente a
cada sucursal.  Los valores aquí tienen prioridad sobre los DEFAULT_*_EMAIL
del .env.

Estructura del JSON:
{
  "branches": {
    "BR-00001": {
      "responsible_email": "tienda001@ejemplo.com"
    },
    "BR-00002": {
      "responsible_email": "tienda002@ejemplo.com"
    }
  },
  "updated_at": "2026-05-27T12:00:00"
}
"""

from typing import Dict, Any, Optional
from datetime import datetime
import json
import os
import logging

logger = logging.getLogger(__name__)

DATA_FILE = os.getenv(
    "BRANCH_CONFIG_FILE",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "branch_config.json",
    ),
)


def _load() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {"branches": {}, "updated_at": None}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("branch_config_service _load: %s", e)
        return {"branches": {}, "updated_at": None}


def _save(data: Dict[str, Any]) -> None:
    data["updated_at"] = datetime.utcnow().isoformat()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all() -> Dict[str, Dict[str, Any]]:
    """Devuelve el mapa completo branch_id → config."""
    return _load().get("branches", {})


def get(branch_id: str) -> Dict[str, Any]:
    """Devuelve la config de una sucursal, o {} si no existe."""
    return _load().get("branches", {}).get(branch_id, {})


def save(branch_id: str, responsible_email: str) -> Dict[str, Any]:
    """Guarda o actualiza el correo responsable de una sucursal."""
    data = _load()
    data.setdefault("branches", {})[branch_id] = {
        "responsible_email": responsible_email.strip(),
    }
    _save(data)
    return data["branches"][branch_id]


def delete(branch_id: str) -> bool:
    """Elimina la config de una sucursal. Devuelve True si existía."""
    data = _load()
    existed = branch_id in data.get("branches", {})
    data.get("branches", {}).pop(branch_id, None)
    if existed:
        _save(data)
    return existed
