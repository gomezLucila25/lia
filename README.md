# LIA Mail Triage

Herramienta **local** que lee tu Gmail, clasifica los mails con Claude y te muestra
un dashboard priorizando vencimientos. Corre en macOS y en Windows.

- **Backend:** Python 3.11+, FastAPI + Uvicorn.
- **Frontend:** una sola página HTML con JS vanilla (sin build step).
- **Gmail:** Gmail API con OAuth 2.0, scope `gmail.readonly` **únicamente** (solo lectura).
- **IA:** dos "cerebros" intercambiables para clasificar:
  - **Gemini `gemini-2.5-flash` — GRATIS** (capa gratuita de Google, sin tarjeta). Recomendado.
  - **Claude `claude-sonnet-5`** — pago (~centavos por análisis).

  LIA elige automáticamente: si está `GEMINI_API_KEY` en el `.env`, usa Gemini (gasto $0).
  Podés forzar uno con `LIA_IA=gemini` o `LIA_IA=claude`.

> LIA solo **lee** tu correo (metadata + snippet). Nunca escribe, responde ni borra nada.

---

## Estructura

```
main.py            # FastAPI: sirve la página y expone POST /api/analizar
gmail_client.py    # Lectura de Gmail (OAuth, solo lectura)
claude_client.py   # Prompt + llamada a Claude + parseo
parser.py          # parse_json_safe (tolerante a truncado) + utilidades de fecha
static/index.html  # Dashboard (una sola página, JS vanilla)
tests/             # pytest: parser y cálculo de días
requirements.txt
.env.example
```

---

## 1. Crear el proyecto en Google Cloud y habilitar Gmail API

1. Entrá a <https://console.cloud.google.com/> y creá un proyecto (o usá uno existente).
2. **APIs y servicios → Biblioteca** → buscá **Gmail API** → **Habilitar**.
3. **APIs y servicios → Pantalla de consentimiento de OAuth**:
   - Tipo de usuario: **Externo**.
   - Completá nombre de la app y tu email.
   - En **Usuarios de prueba**, agregá tu propia dirección de Gmail
     (mientras la app esté en modo "prueba", solo esos usuarios pueden loguearse).
4. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**:
   - Tipo de aplicación: **Aplicación de escritorio**.
   - Descargá el JSON y guardalo en la raíz del proyecto como **`credentials.json`**.

> `credentials.json` y `token.json` están en `.gitignore`: no se commitean.

---

## 2. Crear el `.env` con tu API key

Copiá el ejemplo:

**macOS / Linux**
```bash
cp .env.example .env
```

**Windows (PowerShell)**
```powershell
Copy-Item .env.example .env
```

### Opción GRATIS (recomendada): Gemini
1. Entrá a **https://aistudio.google.com/apikey** con tu cuenta de Google.
2. **Create API key** → copiá la clave. No pide tarjeta.
3. En `.env` poné:
   ```
   GEMINI_API_KEY=tu-clave-de-gemini
   ```

Con eso el análisis real cuesta **$0**. (Nota de privacidad: en la capa gratis
Google puede usar lo enviado para mejorar sus modelos; acá se mandan solo
snippets de tu propio Gmail, que Google ya tiene.)

### Opción paga: Claude
Si preferís Claude, dejá vacío `GEMINI_API_KEY` y poné:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Se paga ~centavos por análisis (créditos prepagos en console.anthropic.com;
dejá el auto-reload apagado para que nunca debite de la tarjeta).

El `.env` está en `.gitignore`.

---

## 3. Instalar dependencias

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea el script de activación, corré una vez:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## 4. Correr la app

```bash
uvicorn main:app --reload
```

Abrí <http://127.0.0.1:8000> y hacé clic en **Analizar mis mails**.

La **primera vez** se abre el navegador para el login de Google (OAuth). Al aceptar,
se crea `token.json` y las siguientes veces no vuelve a pedir login. Si ves una
pantalla de "Google no verificó esta app", es esperable en modo prueba: entrá con
la cuenta que agregaste como usuario de prueba y continuá.

---

## Qué hace el análisis

1. Busca en Gmail:
   - `in:inbox newer_than:7d` (hasta 40 threads),
   - `{vencimiento vence factura resumen "total a pagar" pago} newer_than:30d` (hasta 20 threads).

   Trae solo **metadata + snippet** (no cuerpos completos).
2. Le pide a Claude que devuelva **solo JSON** con vencimientos, acciones,
   informativo y ruido (con límites estrictos de cantidad y largo).
3. El dashboard ordena los **vencimientos** por días restantes:
   `vence HOY` / `vence MAÑANA` (rojo), `en X días` (ámbar si ≤5), `venció hace Xd`
   (rojo), `pagado ✓` (verde), y los sin fecha al final.

Si la respuesta de Claude viene truncada, `parse_json_safe` intenta repararla; si
no hay nada rescatable, la UI muestra *"La respuesta vino incompleta, reintentá"*
(nunca un stack trace).

---

## Modo búsqueda laboral

Además del triage general, LIA tiene un botón aparte **"Búsqueda laboral"** que lee
tus mails de los últimos 60 días (recruiters, RRHH, plataformas de empleo, en
español o inglés) y arma el seguimiento de tus postulaciones:

- **Postulaciones activas** con su estado: *postulada · te respondieron ·
  entrevista agendada · rechazada · oferta · sin respuesta*.
- **Próximas entrevistas**, ordenadas por la más cercana (con chip de días).
- **Te falta completar**: qué tenés pendiente en cada una (responder, formulario, etc.).
- **Te dijeron que no**: los rechazos, colapsados.

Endpoint: `POST /api/busqueda`. Usa el mismo cerebro (Gemini gratis o Claude) y el
mismo modo demo (`LIA_DEMO=1`).

## Recordatorios fijos

El botón **"Recordatorios"** es un tablero de tus vencimientos recurrentes que
cargás vos a mano (alquiler, agua, luz, gas, ADT, expensas, lo que sea). No
dependen del correo: se repiten todos los meses y LIA te avisa cuánto falta
(*vence HOY / MAÑANA / en X días*), ordenados por el más cercano.

- Cargás: concepto + día del mes (1–31) + monto opcional.
- Se guardan localmente en `recordatorios.json` (en `.gitignore`, es info personal).
- Endpoints: `GET/POST /api/recordatorios`, `DELETE /api/recordatorios/{id}`.
- No usa Gmail ni la IA → gratis y funciona siempre.

## Tests

```bash
pytest -q
```

Cubren `parse_json_safe` (JSON sano, truncado a mitad de string, truncado tras
coma, escapes dentro de strings, respuesta sin JSON, truncado antes del primer
cierre) y el cálculo de días restantes (hoy, mañana, pasado, null).

---

## Seguridad

- Scope de Gmail: `gmail.readonly` y nada más.
- `credentials.json`, `token.json` y `.env` están en `.gitignore`.
- Todo corre en tu máquina; los snippets se mandan a la API de Anthropic solo
  para clasificarlos.
