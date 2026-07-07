"""
gmail_client.py — Lectura de Gmail vía Gmail API (OAuth 2.0, flujo instalado).

Scope: gmail.readonly ÚNICAMENTE (nunca escribe ni borra).

Credenciales:
  -credentials.json : OAuth client descargado de Google Cloud Console.
  - token.json       : token de usuario, se crea/refresca en el primer login.

Trae solo metadata (From/Subject/Date) + snippet de cada thread; nunca los
cuerpos completos, para que el prompt quede liviano y no filtremos de más.
"""

import os.path
from email.utils import parseaddr
from urllib.parse import quote

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.readonly y NADA más.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

# Consultas del flujo de análisis.
QUERY_INBOX = "in:inbox newer_than:7d"
QUERY_VENCIMIENTOS = (
    '{vencimiento vence factura resumen "total a pagar" pago} newer_than:30d'
)
MAX_INBOX = 40
MAX_VENCIMIENTOS = 20

# Búsqueda laboral: términos en español e inglés, últimos 60 días.
QUERY_BUSQUEDA = (
    '{postulación postulaste entrevista vacante candidatura recruiter '
    'reclutador "búsqueda laboral" "recursos humanos" application interview '
    '"your application" hiring candidate position} newer_than:60d'
)
MAX_BUSQUEDA = 40


class GmailAuthError(Exception):
    """No se pudo autenticar contra Gmail (falta credentials.json, etc.)."""


def _cargar_credenciales():
    """Carga/refresca las credenciales OAuth, abriendo el navegador si hace
    falta un login inicial."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise GmailAuthError(
                    f"No encontré {CREDENTIALS_FILE}. Descargá el OAuth client "
                    "de Google Cloud Console (ver README)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def _construir_servicio():
    creds = _cargar_credenciales()
    # cache_discovery=False evita warnings/errores en entornos sin caché.
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _header(headers, nombre):
    """Devuelve el valor de un header (case-insensitive) o ''."""
    nombre = nombre.lower()
    for h in headers:
        if h.get("name", "").lower() == nombre:
            return h.get("value", "")
    return ""


def _emisor_legible(from_header):
    """De 'Nombre <mail@dom.com>' devuelve el nombre, o el mail si no hay
    nombre."""
    nombre, email = parseaddr(from_header)
    return nombre.strip() or email.strip() or from_header


def _resumir_mensaje(msg):
    """Convierte un message de la API (formato metadata) al dict liviano que
    le pasamos a Claude."""
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    return {
        "emisor": _emisor_legible(_header(headers, "From")),
        "asunto": _header(headers, "Subject"),
        "fecha": _header(headers, "Date"),
        "snippet": msg.get("snippet", ""),
    }


def _email_cuenta(service):
    """Email de la cuenta autenticada (la que autorizó LIA). Sirve para que los
    links de Gmail apunten SIEMPRE a esa cuenta, sin importar cuál sea la cuenta
    por defecto del navegador."""
    try:
        perfil = service.users().getProfile(userId="me").execute()
        return perfil.get("emailAddress", "")
    except Exception:
        return ""


def _link_gmail(thread_id, email):
    """Link directo a la conversación, fijando la cuenta con authuser."""
    base = f"https://mail.google.com/mail/u/0/"
    ancla = f"#all/{thread_id}"
    if email:
        return f"{base}?authuser={quote(email)}{ancla}"
    return f"{base}{ancla}"


def _buscar_threads(service, query, max_results, email=""):
    """Busca threads por query y devuelve, por cada thread, el primer mensaje
    resumido (metadata + snippet)."""
    resp = (
        service.users()
        .threads()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    threads = resp.get("threads", [])

    resumenes = []
    for t in threads:
        detalle = (
            service.users()
            .threads()
            .get(
                userId="me",
                id=t["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        mensajes = detalle.get("messages", [])
        if not mensajes:
            continue
        # Tomamos el mensaje más reciente del thread para el snippet.
        resumen = _resumir_mensaje(mensajes[-1])
        # Link directo a la conversación en Gmail (para abrir el mail al clickear),
        # fijado a la cuenta autenticada.
        resumen["link"] = _link_gmail(t["id"], email)
        resumenes.append(resumen)
    return resumenes


def obtener_mails():
    """
    Ejecuta las dos búsquedas del flujo y devuelve una lista deduplicada de
    mails resumidos (metadata + snippet), lista para armar el prompt.
    """
    service = _construir_servicio()
    email = _email_cuenta(service)

    inbox = _buscar_threads(service, QUERY_INBOX, MAX_INBOX, email)
    vencimientos = _buscar_threads(service, QUERY_VENCIMIENTOS, MAX_VENCIMIENTOS, email)

    # Dedup por (emisor, asunto, snippet): la búsqueda de vencimientos suele
    # solapar con el inbox.
    vistos = set()
    resultado = []
    for m in inbox + vencimientos:
        clave = (m["emisor"], m["asunto"], m["snippet"])
        if clave in vistos:
            continue
        vistos.add(clave)
        resultado.append(m)
    return resultado


def obtener_mails_busqueda():
    """
    Trae los mails relacionados a búsqueda laboral (metadata + snippet) de los
    últimos 60 días, listos para el análisis de postulaciones.
    """
    service = _construir_servicio()
    email = _email_cuenta(service)
    return _buscar_threads(service, QUERY_BUSQUEDA, MAX_BUSQUEDA, email)
