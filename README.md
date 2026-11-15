# RAR Descompresor API

API REST en **FastAPI + Uvicorn** para descomprimir archivos `.rar` en Linux.
Reutiliza la lógica de extracción del script original (`descomprimir_rar_original.py`
— clase `Motor` / función `extraer`), adaptada a Linux con los motores
`unrar`, `7z` / `7za` y `bsdtar`.

La API está protegida por API key (cabecera `X-API-Key`) y expone un endpoint
para **obtener esa key** y copiarla a un nodo **HTTP Request** de n8n.

---

## Características

- Soporta **RAR5**, archivos con **contraseña** y volúmenes **multiparte** (`.part1.rar`).
- Detección automática de motores en orden de preferencia: **UnRAR → 7-Zip → bsdtar**.
- API key generada en runtime con `secrets.token_urlsafe(32)` y persistida en
  `data/apikey.txt` (en `.gitignore`); nunca se hardcodea ni se commitea.
- Respuestas tipadas con **Pydantic v2**.
- Salida en **JSON** (listado + log) o como **archivo ZIP** con el contenido extraído.

---

## Requisitos e instalación

### 1. Motor RAR del sistema

```bash
sudo apt-get update
sudo apt-get install -y unrar p7zip-full
# Opcionales:
#   sudo apt-get install -y libarchive-tools   # provee bsdtar
#   sudo apt-get install -y rar                # solo si querés CREAR .rar de prueba
```

> `unrar` es el motor preferido (soporta todo). `p7zip-full` provee `7z`/`7za`,
> que también leen RAR. `bsdtar` (libarchive) es el último recurso.

### 2. Dependencias de Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Cómo correr

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Documentación interactiva (Swagger UI): `http://localhost:8000/docs`.

La primera vez que arranca, la app genera la API key y la guarda en
`data/apikey.txt`. También podés fijarla por variable de entorno:

```bash
export RAR_API_KEY="tu-clave"   # tiene prioridad sobre data/apikey.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Endpoints

| Método | Ruta                     | Auth (X-API-Key) | Descripción                                            |
|--------|--------------------------|:----------------:|--------------------------------------------------------|
| GET    | `/health`                | No               | Estado del servicio y motores detectados.              |
| GET    | `/auth/api-key`          | No               | Devuelve la API key vigente (para copiarla a n8n).     |
| POST   | `/auth/api-key/rotate`   | Sí               | Regenera la API key.                                   |
| POST   | `/descomprimir`          | Sí               | Descomprime un `.rar` (salida JSON o ZIP).             |

### `GET /health`

```json
{ "status": "ok", "motores": ["UnRAR", "7-Zip", "bsdtar"] }
```

### `GET /auth/api-key`

```json
{ "api_key": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" }
```

> ⚠️ **Producción:** este endpoint queda accesible sin auth para facilitar el
> desarrollo y la configuración de n8n. En producción deberías **protegerlo o
> deshabilitarlo** (por ejemplo entregando la key por un canal seguro una sola
> vez) y usar `POST /auth/api-key/rotate` para rotarla si se filtra.

### `POST /descomprimir`

`multipart/form-data`:

| Campo            | Tipo        | Obligatorio | Descripción                                   |
|------------------|-------------|:-----------:|-----------------------------------------------|
| `file`           | archivo     | Sí          | El `.rar` a descomprimir.                      |
| `password`       | texto       | No          | Contraseña del archivo.                        |
| `formato_salida` | texto       | No          | `"json"` (por defecto) o `"zip"`.             |

**Ejemplo (JSON):**

```bash
curl -X POST http://localhost:8000/descomprimir \
  -H "X-API-Key: $RAR_API_KEY" \
  -F "file=@prueba.rar"
```

```json
{
  "ok": true,
  "archivos": ["datos.csv", "saludo.txt", "sub/nota.txt"],
  "log": ["▶ prueba.rar  →  ...", "...", "✔ Completado: prueba.rar"]
}
```

**Ejemplo (ZIP):**

```bash
curl -X POST http://localhost:8000/descomprimir \
  -H "X-API-Key: $RAR_API_KEY" \
  -F "file=@prueba.rar" \
  -F "formato_salida=zip" \
  -o extraido.zip
```

**Códigos de error:**

| HTTP | Situación                                             |
|------|-------------------------------------------------------|
| 400  | El archivo no es `.rar`, está vacío, o `formato_salida` inválido. |
| 401  | Falta la cabecera `X-API-Key` o es inválida.          |
| 422  | Error de extracción (contraseña incorrecta, archivo dañado). |
| 500  | No hay ningún motor de extracción instalado.          |

---

## Cómo obtener la API key

```bash
curl -s http://localhost:8000/auth/api-key
# {"api_key":"..."}
```

Copiá ese valor y usalo en la cabecera `X-API-Key` de tus clientes (incluido n8n).

---

## Integración con n8n

Para descomprimir un `.rar` desde un workflow de n8n usá un nodo **HTTP Request**:

1. **Agregá un nodo _HTTP Request_** al workflow.
2. **Method:** `POST`.
3. **URL:** `http://TU_SERVIDOR:8000/descomprimir`
   (reemplazá `TU_SERVIDOR` por la IP/hostname donde corre la API).
4. **Authentication:** `None` (la auth va por header, paso siguiente).
5. **Send Headers:** activalo y agregá:
   - Name: `X-API-Key`
   - Value: la key obtenida en `GET /auth/api-key`.
6. **Send Body:** activalo, **Body Content Type:** `Form-Data (multipart/form-data)`.
   - Parámetro `file` → tipo **n8n Binary File** → Input Data Field Name: el campo
     binario que trae el `.rar` (por ejemplo `data`, el que produce un nodo
     _Read Binary File_ / _Google Drive_ / etc.).
   - (Opcional) Parámetro `password` → tipo **Form Data** → valor: la contraseña.
   - (Opcional) Parámetro `formato_salida` → tipo **Form Data** → valor: `json` o `zip`.
7. Si usás `formato_salida=zip`, en **Options → Response → Response Format**
   elegí `File` para recibir el ZIP como binario.

### JSON de nodo HTTP Request listo para pegar en n8n

Copiá este nodo y pegalo directamente en el canvas de n8n (Ctrl+V).
Ajustá la URL, la `X-API-Key` y el `inputDataFieldName` del binario según tu caso.

```json
{
  "nodes": [
    {
      "parameters": {
        "method": "POST",
        "url": "http://TU_SERVIDOR:8000/descomprimir",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "X-API-Key",
              "value": "PEGAR_AQUI_LA_API_KEY"
            }
          ]
        },
        "sendBody": true,
        "contentType": "multipart-form-data",
        "bodyParameters": {
          "parameters": [
            {
              "parameterType": "formBinaryData",
              "name": "file",
              "inputDataFieldName": "data"
            },
            {
              "parameterType": "formData",
              "name": "formato_salida",
              "value": "json"
            }
          ]
        },
        "options": {}
      },
      "name": "Descomprimir RAR",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [640, 300]
    }
  ],
  "connections": {}
}
```

> Para recibir el contenido como ZIP: cambiá `formato_salida` a `"zip"` y, en el
> nodo, seteá **Options → Response → Response Format = File**.

---

## Estructura del proyecto

```
rar-descompresor-api/
├── app/
│   ├── __init__.py
│   ├── main.py          # App FastAPI y endpoints
│   ├── rar_engine.py    # Port a Linux de Motor/buscar_motores/extraer
│   ├── auth.py          # Generación/persistencia y validación de API key
│   └── models.py        # Modelos Pydantic v2
├── data/                # apikey.txt (generado en runtime, en .gitignore)
├── descomprimir_rar_original.py  # Script original de referencia
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Seguridad

- La API key **nunca** se hardcodea ni se incluye en el repo. Se genera en
  runtime y se guarda en `data/apikey.txt` (ignorado por git).
- `.env.example` no contiene valores reales.
- La validación de la key usa comparación en tiempo constante (`secrets.compare_digest`).
- En producción: protegé/deshabilitá `GET /auth/api-key`, serví la API detrás de
  HTTPS y considerá restringir el tamaño máximo de upload a nivel de proxy.
