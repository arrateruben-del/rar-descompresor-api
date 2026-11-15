"""
Descompresor de archivos RAR
============================

Aplicación con interfaz gráfica (tkinter) para descomprimir archivos .rar
(incluye RAR5, archivos con contraseña y volúmenes multiparte .part1.rar).

No necesita instalar paquetes de Python: usa el primer motor que encuentre:
  1. UnRAR.exe de WinRAR       (recomendado, soporta todo)
  2. 7z.exe de 7-Zip
  3. tar.exe de Windows 10/11  (bsdtar / libarchive)

Uso:
  python descomprimir_rar.py                      -> abre la ventana
  python descomprimir_rar.py archivo.rar [destino] [--password CLAVE]
                                                  -> modo consola
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Motores de extracción
# ---------------------------------------------------------------------------

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class Motor:
    nombre: str
    exe: str

    def comando(self, archivo: Path, destino: Path, password: str | None,
                sobrescribir: bool) -> list[str]:
        if self.nombre == "UnRAR":
            cmd = [self.exe, "x", "-y", "-o+" if sobrescribir else "-o-"]
            cmd.append(f"-p{password}" if password else "-p-")
            cmd += [str(archivo), str(destino) + os.sep]
        elif self.nombre == "7-Zip":
            cmd = [self.exe, "x", "-y", "-aoa" if sobrescribir else "-aos",
                   f"-o{destino}"]
            cmd.append(f"-p{password}" if password else "-p")
            cmd.append(str(archivo))
        else:  # bsdtar
            cmd = [self.exe, "-x", "-v", "-f", str(archivo), "-C", str(destino)]
            if not sobrescribir:
                cmd.append("-k")
            if password:
                cmd += ["--passphrase", password]
        return cmd


def buscar_motores() -> list[Motor]:
    """Devuelve los motores disponibles, en orden de preferencia."""
    pf = [os.environ.get("ProgramFiles", r"C:\Program Files"),
          os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    candidatos = [
        ("UnRAR", [shutil.which("unrar")]
         + [os.path.join(p, "WinRAR", "UnRAR.exe") for p in pf]),
        ("7-Zip", [shutil.which("7z")]
         + [os.path.join(p, "7-Zip", "7z.exe") for p in pf]),
        ("bsdtar", [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                 "System32", "tar.exe")]),
    ]
    motores = []
    for nombre, rutas in candidatos:
        for ruta in rutas:
            if ruta and os.path.isfile(ruta):
                motores.append(Motor(nombre, ruta))
                break
    return motores


MENSAJES_UNRAR = {
    1: "Advertencia: algunos archivos no se extrajeron (quizás ya existían).",
    2: "Error fatal.",
    3: "Error de CRC: archivo dañado o contraseña incorrecta.",
    5: "No se pudo escribir en la carpeta de destino.",
    6: "No se pudo abrir el archivo RAR.",
    9: "No se pudo crear un archivo en el destino.",
    10: "No se encontraron archivos para extraer.",
    11: "Contraseña incorrecta.",
    255: "Operación cancelada.",
}


def extraer(motor: Motor, archivo: Path, destino: Path, password: str | None,
            sobrescribir: bool, log=print) -> bool:
    """Extrae `archivo` en `destino`. Devuelve True si terminó bien."""
    destino.mkdir(parents=True, exist_ok=True)
    cmd = motor.comando(archivo, destino, password, sobrescribir)
    log(f"▶ {archivo.name}  →  {destino}   [{motor.nombre}]")

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
    )
    assert proc.stdout is not None
    for linea_bytes in proc.stdout:
        linea = linea_bytes.decode("cp850", errors="replace").rstrip()
        # Filtramos líneas vacías y los indicadores de % que ensucian el log
        linea = linea.replace("\b", "").strip()
        if linea and not linea.endswith("%"):
            log("   " + linea)
    codigo = proc.wait()

    if codigo == 0:
        log(f"✔ Completado: {archivo.name}\n")
        return True
    detalle = MENSAJES_UNRAR.get(codigo, "") if motor.nombre == "UnRAR" else ""
    log(f"✖ Error ({codigo}) {detalle}\n")
    return False


# ---------------------------------------------------------------------------
# Interfaz gráfica
# ---------------------------------------------------------------------------

def lanzar_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    motores = buscar_motores()

    root = tk.Tk()
    root.title("Descompresor RAR")
    root.geometry("720x520")
    root.minsize(560, 420)

    archivos: list[Path] = []
    var_destino = tk.StringVar()
    var_mismo = tk.BooleanVar(value=True)
    var_subcarpeta = tk.BooleanVar(value=True)
    var_sobrescribir = tk.BooleanVar(value=True)
    var_password = tk.StringVar()
    var_motor = tk.StringVar(value=motores[0].nombre if motores else "")

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    # --- Archivos ---
    ttk.Label(frm, text="Archivos RAR:").grid(row=0, column=0, sticky="nw")
    lista = tk.Listbox(frm, height=5, selectmode="extended")
    lista.grid(row=0, column=1, sticky="nsew", padx=6)
    botones = ttk.Frame(frm)
    botones.grid(row=0, column=2, sticky="n")

    def agregar():
        rutas = filedialog.askopenfilenames(
            title="Elegir archivos RAR",
            filetypes=[("Archivos RAR", "*.rar"), ("Todos", "*.*")])
        for r in rutas:
            p = Path(r)
            if p not in archivos:
                archivos.append(p)
                lista.insert("end", str(p))

    def quitar():
        for i in reversed(lista.curselection()):
            lista.delete(i)
            del archivos[i]

    ttk.Button(botones, text="Agregar…", command=agregar).pack(fill="x")
    ttk.Button(botones, text="Quitar", command=quitar).pack(fill="x", pady=4)

    # --- Destino ---
    ttk.Label(frm, text="Destino:").grid(row=1, column=0, sticky="w", pady=(10, 0))
    ent_dest = ttk.Entry(frm, textvariable=var_destino)
    ent_dest.grid(row=1, column=1, sticky="ew", padx=6, pady=(10, 0))

    def elegir_destino():
        d = filedialog.askdirectory(title="Carpeta de destino")
        if d:
            var_destino.set(d)
            var_mismo.set(False)
            actualizar_destino()

    btn_dest = ttk.Button(frm, text="Examinar…", command=elegir_destino)
    btn_dest.grid(row=1, column=2, sticky="ew", pady=(10, 0))

    def actualizar_destino():
        estado = "disabled" if var_mismo.get() else "normal"
        ent_dest.configure(state=estado)

    opciones = ttk.Frame(frm)
    opciones.grid(row=2, column=1, sticky="w", padx=6, pady=4)
    ttk.Checkbutton(opciones, text="Misma carpeta que el RAR", variable=var_mismo,
                    command=actualizar_destino).pack(anchor="w")
    ttk.Checkbutton(opciones, text="Crear subcarpeta con el nombre del archivo",
                    variable=var_subcarpeta).pack(anchor="w")
    ttk.Checkbutton(opciones, text="Sobrescribir archivos existentes",
                    variable=var_sobrescribir).pack(anchor="w")
    actualizar_destino()

    # --- Contraseña y motor ---
    ttk.Label(frm, text="Contraseña:").grid(row=3, column=0, sticky="w")
    ttk.Entry(frm, textvariable=var_password, show="•").grid(
        row=3, column=1, sticky="ew", padx=6)
    ttk.Label(frm, text="(opcional)").grid(row=3, column=2, sticky="w")

    ttk.Label(frm, text="Motor:").grid(row=4, column=0, sticky="w", pady=6)
    cmb = ttk.Combobox(frm, textvariable=var_motor, state="readonly",
                       values=[m.nombre for m in motores])
    cmb.grid(row=4, column=1, sticky="w", padx=6, pady=6)

    # --- Log ---
    log_txt = ScrolledText(frm, height=10, font=("Consolas", 9), state="disabled")
    log_txt.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
    frm.rowconfigure(6, weight=1)

    def log(msg: str):
        def _add():
            log_txt.configure(state="normal")
            log_txt.insert("end", msg + "\n")
            log_txt.see("end")
            log_txt.configure(state="disabled")
        root.after(0, _add)

    barra = ttk.Progressbar(frm, mode="determinate")
    barra.grid(row=7, column=0, columnspan=3, sticky="ew", pady=6)

    def descomprimir():
        if not archivos:
            messagebox.showwarning("Descompresor RAR", "Agregá al menos un archivo RAR.")
            return
        if not var_mismo.get() and not var_destino.get().strip():
            messagebox.showwarning("Descompresor RAR", "Elegí una carpeta de destino.")
            return
        motor = next(m for m in motores if m.nombre == var_motor.get())
        btn_go.configure(state="disabled")
        barra.configure(maximum=len(archivos), value=0)

        def trabajo():
            ok = 0
            for i, arch in enumerate(list(archivos), 1):
                base = arch.parent if var_mismo.get() else Path(var_destino.get())
                destino = base / nombre_base(arch) if var_subcarpeta.get() else base
                try:
                    if extraer(motor, arch, destino, var_password.get() or None,
                               var_sobrescribir.get(), log):
                        ok += 1
                except Exception as e:  # noqa: BLE001
                    log(f"✖ {arch.name}: {e}\n")
                root.after(0, lambda v=i: barra.configure(value=v))
            total = len(archivos)

            def fin():
                btn_go.configure(state="normal")
                messagebox.showinfo("Descompresor RAR",
                                    f"Terminado: {ok} de {total} archivo(s) extraídos.")
            root.after(0, fin)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_go = ttk.Button(frm, text="Descomprimir", command=descomprimir)
    btn_go.grid(row=5, column=0, columnspan=3, pady=(4, 0))

    if not motores:
        btn_go.configure(state="disabled")
        log("No se encontró ningún motor (WinRAR, 7-Zip o tar.exe de Windows).\n"
            "Instalá WinRAR o 7-Zip y volvé a abrir la aplicación.")
    else:
        log("Motores disponibles: " + ", ".join(f"{m.nombre} ({m.exe})" for m in motores))

    root.mainloop()


def nombre_base(archivo: Path) -> str:
    """'datos.part1.rar' -> 'datos';  'fotos.rar' -> 'fotos'."""
    nombre = archivo.stem
    partes = nombre.rsplit(".", 1)
    if len(partes) == 2 and partes[1].lower().startswith("part"):
        nombre = partes[0]
    return nombre


# ---------------------------------------------------------------------------
# Modo consola
# ---------------------------------------------------------------------------

def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        if flujo is not None and hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    if len(sys.argv) == 1:
        lanzar_gui()
        return 0

    ap = argparse.ArgumentParser(description="Descomprime archivos RAR.")
    ap.add_argument("archivo", type=Path, help="archivo .rar")
    ap.add_argument("destino", type=Path, nargs="?",
                    help="carpeta destino (por defecto: junto al RAR, en una subcarpeta)")
    ap.add_argument("-p", "--password", help="contraseña del archivo")
    ap.add_argument("--no-sobrescribir", action="store_true",
                    help="no reemplazar archivos existentes")
    args = ap.parse_args()

    motores = buscar_motores()
    if not motores:
        print("No se encontró WinRAR, 7-Zip ni tar.exe de Windows.", file=sys.stderr)
        return 2
    if not args.archivo.is_file():
        print(f"No existe: {args.archivo}", file=sys.stderr)
        return 2

    destino = args.destino or args.archivo.parent / nombre_base(args.archivo)
    ok = extraer(motores[0], args.archivo.resolve(), destino.resolve(),
                 args.password, not args.no_sobrescribir)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
