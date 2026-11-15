"""
Gestión y validación de la API key.

La key:
  - Se toma de la variable de entorno RAR_API_KEY si está definida.
  - Si no, se persiste/lee desde data/apikey.txt (en .gitignore).
  - Si no existe, se genera con secrets.token_urlsafe(32) la primera vez.

Nunca se hardcodea ni se commitea al repositorio.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, status

# data/apikey.txt junto a la raíz del proyecto (../data respecto a app/).
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_APIKEY_FILE = _DATA_DIR / "apikey.txt"


def _generar_key() -> str:
    return secrets.token_urlsafe(32)


def _leer_archivo() -> str | None:
    if _APIKEY_FILE.is_file():
        contenido = _APIKEY_FILE.read_text(encoding="utf-8").strip()
        return contenido or None
    return None


def _guardar_archivo(key: str) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _APIKEY_FILE.write_text(key, encoding="utf-8")
    # Permisos restrictivos (solo el dueño puede leer/escribir).
    try:
        os.chmod(_APIKEY_FILE, 0o600)
    except OSError:
        pass


def obtener_api_key() -> str:
    """Devuelve la API key vigente, generándola y persistiéndola si hace falta.

    Prioridad: variable de entorno RAR_API_KEY > data/apikey.txt > nueva.
    """
    env_key = os.environ.get("RAR_API_KEY", "").strip()
    if env_key:
        return env_key

    key = _leer_archivo()
    if key:
        return key

    key = _generar_key()
    _guardar_archivo(key)
    return key


def rotar_api_key() -> str:
    """Genera una nueva API key y la persiste en el archivo de datos.

    Nota: si RAR_API_KEY está fijada por entorno, esta seguirá teniendo
    prioridad en obtener_api_key(); la rotación afecta al archivo de datos.
    """
    key = _generar_key()
    _guardar_archivo(key)
    return key


async def validar_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Dependencia de FastAPI que valida la cabecera X-API-Key.

    Lanza 401 si falta o no coincide con la key vigente.
    """
    vigente = obtener_api_key()
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera X-API-Key.",
        )
    # Comparación en tiempo constante para evitar ataques de temporización.
    if not secrets.compare_digest(x_api_key, vigente):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida.",
        )
    return x_api_key
