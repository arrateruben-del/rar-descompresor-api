"""
API REST para descomprimir archivos RAR.

Envuelve la lógica de extracción de `rar_engine.py` (port a Linux del script
original) y expone endpoints protegidos por API key (cabecera X-API-Key),
pensados para integrarse con un nodo HTTP Request de n8n.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app import rar_engine
from app.auth import obtener_api_key, rotar_api_key, validar_api_key
from app.models import (
    ApiKeyResponse,
    DescomprimirResponse,
    HealthResponse,
)

app = FastAPI(
    title="RAR Descompresor API",
    description=(
        "API REST para descomprimir archivos .rar en Linux. "
        "Reutiliza la lógica de extracción del script original, adaptada a "
        "los motores unrar / 7z / bsdtar. Protegida por cabecera X-API-Key."
    ),
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse, tags=["estado"])
async def health() -> HealthResponse:
    """Estado del servicio y motores de extracción detectados (sin auth)."""
    motores = [m.nombre for m in rar_engine.buscar_motores()]
    return HealthResponse(status="ok", motores=motores)


@app.get("/auth/api-key", response_model=ApiKeyResponse, tags=["autenticación"])
async def get_api_key() -> ApiKeyResponse:
    """Devuelve la API key vigente (para copiarla a n8n).

    En desarrollo este endpoint queda accesible. En producción debería
    protegerse o deshabilitarse (ver README).
    """
    return ApiKeyResponse(api_key=obtener_api_key())


@app.post(
    "/auth/api-key/rotate",
    response_model=ApiKeyResponse,
    tags=["autenticación"],
    dependencies=[Depends(validar_api_key)],
)
async def rotate_api_key() -> ApiKeyResponse:
    """Regenera la API key (requiere la X-API-Key vigente)."""
    return ApiKeyResponse(api_key=rotar_api_key())


@app.post(
    "/descomprimir",
    tags=["descompresión"],
    dependencies=[Depends(validar_api_key)],
    responses={
        200: {"description": "Extracción correcta (JSON o archivo ZIP)."},
        400: {"description": "Petición inválida (archivo no .rar, etc.)."},
        401: {"description": "API key ausente o inválida."},
        422: {"description": "Error de extracción (contraseña, archivo dañado)."},
        500: {"description": "No hay motor de extracción disponible."},
    },
)
async def descomprimir(
    file: UploadFile = File(..., description="Archivo .rar a descomprimir."),
    password: str | None = Form(default=None, description="Contraseña (opcional)."),
    formato_salida: str = Form(
        default="json",
        description='Formato de salida: "json" (por defecto) o "zip".',
    ),
):
    """Descomprime un archivo .rar subido vía multipart/form-data."""
    formato = (formato_salida or "json").strip().lower()
    if formato not in ("json", "zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='El campo formato_salida debe ser "json" o "zip".',
        )

    nombre = file.filename or "archivo"
    if not nombre.lower().endswith(".rar"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener extensión .rar.",
        )

    motores = rar_engine.buscar_motores()
    if not motores:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "No hay ningún motor de extracción disponible en el servidor "
                "(instalá unrar o p7zip-full)."
            ),
        )

    # Directorio temporal aislado por petición.
    tmpdir = Path(tempfile.mkdtemp(prefix="rar_api_"))
    try:
        rar_path = tmpdir / Path(nombre).name
        destino = tmpdir / "extraido"
        destino.mkdir(parents=True, exist_ok=True)

        # Guardamos el upload en disco.
        with rar_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        if rar_path.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo subido está vacío.",
            )

        ok, log, archivos = rar_engine.extraer(
            motores[0],
            rar_path,
            destino,
            password=password or None,
            sobrescribir=True,
        )

        if not ok:
            # Deducimos un mensaje útil del log.
            detalle = next(
                (l.strip() for l in reversed(log) if l.strip().startswith("✖")),
                "No se pudo extraer el archivo.",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=detalle.lstrip("✖ ").strip() or "No se pudo extraer el archivo.",
            )

        if formato == "zip":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel in archivos:
                    zf.write(destino / rel, arcname=rel)
            buffer.seek(0)
            zip_name = f"{rar_engine.nombre_base(rar_path)}.zip"
            return StreamingResponse(
                io.BytesIO(buffer.read()),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{zip_name}"'
                },
            )

        return DescomprimirResponse(ok=True, archivos=archivos, log=log)
    finally:
        try:
            file.file.close()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)
