"""
Motor de extracción de archivos RAR — port a Linux.

Adaptación de la lógica de `descomprimir_rar_original.py` (clase Motor /
función extraer) para ejecutarse en Linux, detectando los binarios
`unrar`, `7z`, `7za` y `bsdtar` disponibles en el sistema.

A diferencia del script original (orientado a GUI/CLI de Windows), este
módulo expone `extraer()` devolviendo una tupla estructurada
`(ok: bool, log: list[str], archivos_extraidos: list[str])` pensada para
ser consumida por la API FastAPI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Motores de extracción
# ---------------------------------------------------------------------------

@dataclass
class Motor:
    """Representa un motor de extracción (binario) disponible en el sistema."""

    nombre: str  # "UnRAR", "7-Zip" o "bsdtar"
    exe: str     # ruta absoluta al binario

    def comando(
        self,
        archivo: Path,
        destino: Path,
        password: str | None,
        sobrescribir: bool,
    ) -> list[str]:
        """Construye la lista de argumentos para ejecutar el motor."""
        if self.nombre == "UnRAR":
            cmd = [self.exe, "x", "-y", "-o+" if sobrescribir else "-o-"]
            # -p<clave> con contraseña; -p- para no preguntar nunca.
            cmd.append(f"-p{password}" if password else "-p-")
            cmd += [str(archivo), str(destino) + os.sep]
        elif self.nombre == "7-Zip":
            cmd = [
                self.exe,
                "x",
                "-y",
                "-aoa" if sobrescribir else "-aos",
                f"-o{destino}",
            ]
            # 7z: -p sin valor fuerza modo no interactivo sin contraseña.
            cmd.append(f"-p{password}" if password else "-p")
            cmd.append(str(archivo))
        else:  # bsdtar (libarchive)
            cmd = [self.exe, "-x", "-v", "-f", str(archivo), "-C", str(destino)]
            if not sobrescribir:
                cmd.append("-k")
            if password:
                cmd += ["--passphrase", password]
        return cmd


def buscar_motores() -> list[Motor]:
    """Devuelve los motores disponibles en Linux, en orden de preferencia.

    UnRAR es el preferido (soporta RAR5, multiparte y contraseña por completo),
    luego 7-Zip (7z/7za) y por último bsdtar (libarchive).
    """
    candidatos: list[tuple[str, list[str | None]]] = [
        ("UnRAR", [shutil.which("unrar")]),
        ("7-Zip", [shutil.which("7z"), shutil.which("7za")]),
        ("bsdtar", [shutil.which("bsdtar")]),
    ]
    motores: list[Motor] = []
    for nombre, rutas in candidatos:
        for ruta in rutas:
            if ruta and os.path.isfile(ruta):
                motores.append(Motor(nombre, ruta))
                break
    return motores


# Mapeo de códigos de salida de UnRAR a mensajes claros en español.
MENSAJES_UNRAR = {
    1: "Advertencia: algunos archivos no se extrajeron (quizás ya existían).",
    2: "Error fatal durante la extracción.",
    3: "Error de CRC: archivo dañado o contraseña incorrecta.",
    5: "No se pudo escribir en la carpeta de destino.",
    6: "No se pudo abrir el archivo RAR.",
    9: "No se pudo crear un archivo en el destino.",
    10: "No se encontraron archivos para extraer.",
    11: "Contraseña incorrecta.",
    255: "Operación cancelada.",
}


def _listar_archivos(destino: Path) -> list[str]:
    """Lista recursivamente los archivos extraídos (rutas relativas a destino)."""
    extraidos: list[str] = []
    for root, _dirs, files in os.walk(destino):
        for f in files:
            ruta = Path(root) / f
            extraidos.append(str(ruta.relative_to(destino)))
    extraidos.sort()
    return extraidos


def extraer(
    motor: Motor,
    archivo: Path,
    destino: Path,
    password: str | None = None,
    sobrescribir: bool = True,
) -> tuple[bool, list[str], list[str]]:
    """Extrae `archivo` en `destino` usando `motor`.

    Devuelve una tupla:
      - ok: True si la extracción terminó correctamente.
      - log: lista de líneas de log (salida del motor + mensajes).
      - archivos_extraidos: rutas relativas de los archivos obtenidos.
    """
    log: list[str] = []
    destino.mkdir(parents=True, exist_ok=True)
    cmd = motor.comando(archivo, destino, password, sobrescribir)
    log.append(f"▶ {archivo.name}  →  {destino}   [{motor.nombre}]")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        log.append(f"✖ No se encontró el binario del motor: {motor.exe}")
        return False, log, []

    assert proc.stdout is not None
    for linea_bytes in proc.stdout:
        # UnRAR en Linux suele emitir UTF-8; usamos utf-8 con fallback.
        linea = linea_bytes.decode("utf-8", errors="replace").rstrip()
        linea = linea.replace("\b", "").strip()
        if linea and not linea.endswith("%"):
            log.append("   " + linea)
    codigo = proc.wait()

    archivos_extraidos = _listar_archivos(destino)

    if codigo == 0:
        log.append(f"✔ Completado: {archivo.name}")
        return True, log, archivos_extraidos

    detalle = MENSAJES_UNRAR.get(codigo, "") if motor.nombre == "UnRAR" else ""
    log.append(f"✖ Error ({codigo}) {detalle}".rstrip())
    return False, log, archivos_extraidos


def nombre_base(archivo: Path) -> str:
    """'datos.part1.rar' -> 'datos';  'fotos.rar' -> 'fotos'."""
    nombre = archivo.stem
    partes = nombre.rsplit(".", 1)
    if len(partes) == 2 and partes[1].lower().startswith("part"):
        nombre = partes[0]
    return nombre
