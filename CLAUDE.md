# CLAUDE.md — Guía del proyecto LIA

Esta guía es para retomar el proyecto en cualquier máquina (incluida la Mac) y
para futuras sesiones con Claude. Explica **qué es**, **cómo correrlo**, **qué
tiene hoy** y **qué queremos agregar**.

---

## Qué es LIA

**LIA Mail Triage** es un dashboard personal y **local** que junta en un solo
lugar "todo lo que cuesta seguir": vencimientos que llegan por mail, la búsqueda
laboral, y los gastos fijos con sus comprobantes. Lee el Gmail en **solo lectura**,
clasifica con IA y muestra todo priorizado por lo que vence primero.

Objetivo de diseño: **simplificarle la vida a una persona olvidadiza.** LIA es la
memoria; el usuario no tiene que acordarse de nada.

- Idioma de la UI y de la IA: **castellano rioplatense**.
- Corre en **macOS y Windows**.
- **Sin build step** en el front (HTML + JS vanilla).

---

## Stack

- **Python 3.11+**, **FastAPI + Uvicorn**.
- **Frontend**: una sola página, `static/index.html` (JS vanilla, sin framework).
- **Gmail**: Gmail API con OAuth 2.0 (flujo instalado), scope `gmail.readonly` **únicamente**.
- **IA (dos backends intercambiables)**:
  - **Gemini `gemini-2.5-flash` — GRATIS** (capa gratuita de Google, sin tarjeta). *Default.*
  - **Claude `claude-sonnet-5`** — pago (~centavos por análisis), con `thinking` desactivado
    para no gastar el budget de tokens del JSON.
  - Selección automática: si hay `GEMINI_API_KEY` en el `.env`, usa Gemini. Forzar con
    `LIA_IA=gemini` o `LIA_IA=claude`.

---

## Estructura de archivos

```
main.py            # FastAPI: rutas y orquestación
gmail_client.py    # Lectura de Gmail (OAuth, solo lectura, links a cada mail)
claude_client.py   # Prompts + schemas + llamada a Claude (fuente de verdad de los prompts)
gemini_client.py   # Mismos análisis con Gemini (reutiliza prompts de claude_client)
parser.py          # parse_json_safe (tolerante a JSON truncado) + dias_restantes
recordatorios.py   # Recordatorios fijos mensuales (guardados en recordatorios.json)
comprobantes.py    # Comprobantes de pago adjuntos (guardados en comprobantes/<id>/)
static/index.html  # Toda la UI (3 botones: triage, búsqueda laboral, recordatorios)
tests/             # pytest: parser y cálculo de días
requirements.txt
.env.example       # Plantilla de variables (copiar a .env)
README.md          # Guía de instalación paso a paso (Google Cloud, Gemini, etc.)
CLAUDE.md          # Este archivo
```

### Archivos que NO están en git (secretos / datos personales)
Están en `.gitignore` y hay que crearlos/copiarlos a mano en cada máquina:

- `.env` — claves (`GEMINI_API_KEY`, opcional `ANTHROPIC_API_KEY`).
- `credentials.json` — cliente OAuth de Google (se descarga de Google Cloud).
- `token.json` — token de sesión de Gmail (se crea solo en el primer login).
- `recordatorios.json` — los recordatorios fijos cargados.
- `comprobantes/` — los archivos de comprobantes subidos.

---

## Cómo correrlo

### Setup en una máquina nueva (ej: la Mac)
1. Clonar el repo: `git clone https://github.com/gomezLucila25/lia.git`
2. Crear el entorno e instalar dependencias:
   - **macOS**: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
   - **Windows**: `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt`
3. Crear `.env` (copiar `.env.example` a `.env`) y poner `GEMINI_API_KEY=...`
   (se saca gratis en https://aistudio.google.com/apikey).
4. Poner `credentials.json` en la raíz (se descarga de Google Cloud Console — ver README).
5. Correr: `uvicorn main:app --reload` y abrir http://127.0.0.1:8000
6. En "Analizar", la primera vez se abre el login de Google (se crea `token.json`).

> Para **conservar tus datos** entre máquinas, copiá también `recordatorios.json`
> y la carpeta `comprobantes/`. O usá el botón **Exportar/Importar backup** de la
> sección Recordatorios.

### Modo demo (GRATIS, sin correo ni IA)
Con `LIA_DEMO=1` LIA no toca Gmail ni la IA y muestra datos de ejemplo. Sirve para
probar la interfaz sin gastar ni loguearse:
- **Windows**: `$env:LIA_DEMO="1"; uvicorn main:app --reload`
- **macOS**: `LIA_DEMO=1 uvicorn main:app --reload`

---

## Funcionalidades actuales

### 0. Resumen  ·  `POST /api/resumen`
- Pantallazo combinado de "esta semana": junta vencimientos del correo + recordatorios
  fijos + próximas entrevistas + pendientes de laburo en una sola vista (hero con tiles
  + timeline "Lo que se viene" ordenada por lo más cercano).
- Corre triage + búsqueda laboral + recordatorios en una sola llamada (tarda unos segundos).

### 1. Analizar mis mails (triage)  ·  `POST /api/analizar`
- Busca inbox 7d (hasta 40) + vencimientos 30d (hasta 20). Solo metadata + snippet.
- La IA clasifica en: **vencimientos** (con estado pendiente/débito automático/pagado),
  **acción**, **informativo**, y cuenta el **ruido**.
- Ordena vencimientos por días restantes, con chips (vence HOY/MAÑANA/en X días/venció/pagado).
- **Los recordatorios fijos aparecen también acá**, mezclados en "Vencimientos" (marcados con 🔁).
- Cada tarjeta que viene de un mail es **clickeable y abre ese correo en Gmail**, fijado a
  la cuenta autenticada (`authuser=<tu-email>`).

### 2. Búsqueda laboral  ·  `POST /api/busqueda`
- Busca mails de laburo (español/inglés) de los últimos 60 días.
- Arma el seguimiento de **postulaciones** con estado: postulada / te respondieron /
  entrevista agendada / rechazada / oferta / sin respuesta.
- Vistas: Próximas entrevistas, Te falta completar (pendientes), Postulaciones activas,
  y "Te dijeron que no" (rechazos, colapsado).
- Tarjetas clickeables al mail.

### 3. Recordatorios fijos  ·  `GET/POST /api/recordatorios`, `DELETE /api/recordatorios/{id}`
- Gastos recurrentes cargados a mano (alquiler, agua, luz, gas, ADT, expensas, etc.):
  concepto + día del mes + monto opcional.
- Se guardan en `recordatorios.json` (disco local; sobreviven cierre de página y apagado).
- Chips de "vence en X días". No usan Gmail ni IA → gratis.
- **Marcar como pagado** por mes (`POST /api/recordatorios/{id}/pagado`): chip verde "pagado ✓";
  se resetea solo el mes siguiente. Subir un comprobante marca pagado automáticamente.
- **Backup**: Exportar / Importar (`POST /api/recordatorios/importar`).
- **Comprobantes de pago (Drive local)**: subir/ver/borrar archivos por recordatorio.
  - `POST /api/recordatorios/{id}/comprobantes` (multipart)
  - `GET  /api/recordatorios/{id}/comprobantes/{nombre}` (descarga; protegido contra path traversal)
  - `DELETE /api/recordatorios/{id}/comprobantes/{nombre}`

### Robustez
- `parse_json_safe`: repara JSON truncado (por si la IA se corta). Si no hay nada
  rescatable, la UI muestra "la respuesta vino incompleta, reintentá" (nunca un stack trace).
- Todos los errores del backend vuelven como JSON amigable con el status adecuado.

---

## Qué queremos agregar (roadmap)

Ideas charladas, ordenadas por impacto. **Ninguna está hecha todavía** salvo lo de
"recordatorios dentro de vencimientos" (ya está).

**Próximo / alto impacto**
- [x] **Resumen arriba de todo** — HECHO (botón "Resumen", `/api/resumen`).
- [x] **Marcar recordatorio como "pagado este mes"** — HECHO (chip verde; se marca solo
      al subir el comprobante; se resetea al mes siguiente).
- [ ] **Follow-up sugerido** en búsqueda laboral: para postulaciones sin respuesta hace
      mucho, un borrador de mail listo para copiar.

**Media**
- [ ] **Historial de pagos** por recordatorio (mes a mes, con su comprobante).
- [ ] **Editar** un recordatorio (hoy solo se agrega/borra).
- [ ] **Notificaciones/alertas** (mail o del navegador) cuando algo vence pronto.
- [ ] **Categorías/etiquetas** y filtros en las tres vistas.
- [ ] **Agregar postulaciones a mano** (por si la IA no detecta alguna).

**Futuro / nice-to-have**
- [ ] Soporte multi-cuenta de Gmail.
- [ ] Un login simple si algún día se hostea (hoy es 100% local).
- [ ] Recordatorios que no sean mensuales (anuales, únicos, cada X meses).
- [ ] Exportar el dashboard a PDF / resumen semanal por mail.

---

## Convenciones (para mantener consistencia)

- **UI e IA en castellano rioplatense.** Comentarios de código en español.
- **Sin build step**: todo el front en `static/index.html`, JS vanilla.
- **Prompts y schemas viven en `claude_client.py`**; `gemini_client.py` los reutiliza.
  Si cambia el schema, tocar un solo lugar.
- **Seguridad**: scope Gmail solo lectura; nunca commitear `.env`, `credentials.json`,
  `token.json`, `recordatorios.json` ni `comprobantes/`. Sanear nombres de archivo
  subidos (ver `comprobantes._nombre_seguro`).
- **max_tokens 4000** en la IA (con 1000 se truncaba el JSON; no bajar).
- **Modelo Claude**: `claude-sonnet-5` con `thinking` desactivado. **Gemini**: `gemini-2.5-flash`.

## Tests

```bash
pytest -q
```
Cubren `parse_json_safe` (JSON sano, truncados, escapes, sin-JSON) y `dias_restantes`.
Los endpoints de recordatorios/comprobantes se probaron a mano (no requieren Gmail ni IA).
```
