"""
gemini_client.py — Clasificación de mails con Google Gemini (capa GRATIS).

Alternativa sin costo a claude_client. Expone los mismos dos análisis:
  - analizar_mails(mails)
  - analizar_busqueda_laboral(mails)

Reutiliza prompts y schemas de claude_client (una sola fuente de verdad) y el
parser tolerante del proyecto.

- Modelo: gemini-2.5-flash (rápido y dentro de la capa gratis).
- max_output_tokens: 4000. response_mime_type=application/json.
- API key desde GEMINI_API_KEY (.env). Sacala en https://aistudio.google.com/apikey
"""

import os

from google import genai
from google.genai import types
from dotenv import load_dotenv

from parser import parse_json_safe
from claude_client import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_BUSQUEDA,
    SYSTEM_PROMPT_FOLLOWUP,
    _armar_prompt,
    _armar_prompt_busqueda,
    _armar_prompt_followup,
)

load_dotenv()

MODELO = "gemini-2.5-flash"
MAX_TOKENS = 4000


class GeminiConfigError(Exception):
    """Falta configuración para usar Gemini (p. ej. GEMINI_API_KEY)."""


def _completar(system, prompt):
    """Llama a Gemini una vez y devuelve el texto de la respuesta."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiConfigError(
            "Falta GEMINI_API_KEY. Sacá una gratis en "
            "https://aistudio.google.com/apikey y ponela en el .env (ver README)."
        )

    client = genai.Client(api_key=api_key)
    respuesta = client.models.generate_content(
        model=MODELO,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            max_output_tokens=MAX_TOKENS,
            temperature=0,
        ),
    )
    return respuesta.text or ""


def analizar_mails(mails):
    """Triage general. Devuelve el dict del schema del proyecto."""
    return parse_json_safe(_completar(SYSTEM_PROMPT, _armar_prompt(mails)))


def analizar_busqueda_laboral(mails):
    """Seguimiento de postulaciones. Devuelve el dict del schema de búsqueda."""
    return parse_json_safe(
        _completar(SYSTEM_PROMPT_BUSQUEDA, _armar_prompt_busqueda(mails))
    )


def redactar_followup(post):
    """Genera un borrador {asunto, cuerpo} de mail de seguimiento con Gemini."""
    return parse_json_safe(
        _completar(SYSTEM_PROMPT_FOLLOWUP, _armar_prompt_followup(post))
    )
