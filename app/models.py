"""Modelos Pydantic v2 para las respuestas de la API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Respuesta de GET /health."""

    status: str = Field(default="ok", description="Estado del servicio.")
    motores: list[str] = Field(
        default_factory=list,
        description="Motores de extracción RAR detectados en el sistema.",
    )


class ApiKeyResponse(BaseModel):
    """Respuesta con la API key vigente."""

    api_key: str = Field(description="API key vigente para la cabecera X-API-Key.")


class DescomprimirResponse(BaseModel):
    """Respuesta de POST /descomprimir con formato_salida=json."""

    ok: bool = Field(description="True si la extracción terminó correctamente.")
    archivos: list[str] = Field(
        default_factory=list,
        description="Rutas relativas de los archivos extraídos.",
    )
    log: list[str] = Field(
        default_factory=list,
        description="Líneas de log de la extracción.",
    )


class ErrorResponse(BaseModel):
    """Respuesta de error estándar."""

    detail: str = Field(description="Descripción del error en español.")
