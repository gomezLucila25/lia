"""
claude_client.py — Clasificación de mails con Claude.

Expone dos análisis, ambos devuelven JSON parseado con parse_json_safe:
  - analizar_mails(mails)             -> triage general (vencimientos/acción/...).
  - analizar_busqueda_laboral(mails)  -> seguimiento de postulaciones.

- Modelo: claude-sonnet-5 (elección explícita del proyecto).
- max_tokens: 4000 (con 1000 ya sufrimos JSON truncado; no repetir).
- thinking desactivado: en sonnet-5 el thinking adaptativo viene prendido por
  defecto y nos comería tokens del budget de 4000 -> más riesgo de truncado.
- API key desde ANTHROPIC_API_KEY (.env + python-dotenv).

Nota: los prompts y schemas viven acá y gemini_client los reutiliza, así hay
una sola fuente de verdad.
"""

import os

import anthropic
from dotenv import load_dotenv

from parser import parse_json_safe

load_dotenv()

MODELO = "claude-sonnet-5"
MAX_TOKENS = 4000

# ------------------------- Triage general -------------------------

SCHEMA_EJEMPLO = """{
  "vencimientos": [{"titulo": str, "emisor": str, "fecha": "YYYY-MM-DD"|null, "detalle": str, "estado": "pendiente"|"debito_automatico"|"pagado", "ref": int}],
  "accion": [{"titulo": str, "emisor": str, "detalle": str, "ref": int}],
  "informativo": [{"titulo": str, "emisor": str, "detalle": str, "ref": int}],
  "ruido_count": int,
  "ruido_ejemplos": [str]
}"""

SYSTEM_PROMPT = (
    "Sos LIA, una asistente que triaja el correo de una persona en Argentina. "
    "Hablás en castellano rioplatense, natural y directo. "
    "Respondés ÚNICAMENTE con JSON válido, sin texto antes ni después, "
    "sin fences de markdown."
)

# ------------------------- Búsqueda laboral -------------------------

SCHEMA_BUSQUEDA = """{
  "postulaciones": [{
    "empresa": str,
    "puesto": str,
    "fecha": "YYYY-MM-DD"|null,
    "estado": "postulada"|"respondieron"|"entrevista_agendada"|"rechazada"|"oferta"|"sin_respuesta",
    "pendiente": str,
    "proxima_fecha": "YYYY-MM-DD"|null,
    "detalle": str,
    "ref": int
  }]
}"""

SYSTEM_PROMPT_BUSQUEDA = (
    "Sos LIA, una asistente que sigue la búsqueda laboral de una persona en "
    "Argentina a partir de su correo. Los mails pueden estar en español o en "
    "inglés (recruiters, LinkedIn, RRHH, plataformas de empleo). "
    "Hablás en castellano rioplatense. Respondés ÚNICAMENTE con JSON válido, "
    "sin texto antes ni después, sin fences de markdown."
)


def _armar_prompt(mails):
    """Prompt del triage general."""
    lineas = []
    for i, m in enumerate(mails, start=1):
        lineas.append(
            f"[{i}] De: {m.get('emisor', '')} | Asunto: {m.get('asunto', '')} | "
            f"Fecha: {m.get('fecha', '')}\n    {m.get('snippet', '')}"
        )
    listado = "\n".join(lineas) if lineas else "(no hay mails)"

    return f"""Te paso {len(mails)} mails (metadata + snippet). Clasificálos y devolvé
SOLO este JSON:

{SCHEMA_EJEMPLO}

Reglas estrictas:
- Máximo 6 items en "vencimientos", 5 en "accion", 5 en "informativo".
- Cada "detalle": máximo 12 palabras, castellano rioplatense.
- "vencimientos": cosas con plata a pagar o fecha límite. Si detectás débito
  automático, estado "debito_automatico"; si ya se pagó, "pagado"; si no,
  "pendiente". "fecha" en formato YYYY-MM-DD o null si no hay fecha clara.
- "accion": mails que requieren que la persona haga algo (responder, gestionar),
  sin plata de por medio.
- "informativo": novedades relevantes que NO requieren acción.
- "ruido_count": cuántos mails son ruido (promos, newsletters, notificaciones
  automáticas). "ruido_ejemplos": hasta 3 asuntos de ejemplo del ruido.
- Todo mail entra en exactamente una categoría o cuenta como ruido.
- En cada item de vencimientos/accion/informativo incluí "ref": el número [n]
  del mail de origen (el principal si el item resume varios). Es obligatorio.

Mails:
{listado}
"""


def _armar_prompt_busqueda(mails):
    """Prompt del seguimiento de postulaciones."""
    lineas = []
    for i, m in enumerate(mails, start=1):
        lineas.append(
            f"[{i}] De: {m.get('emisor', '')} | Asunto: {m.get('asunto', '')} | "
            f"Fecha: {m.get('fecha', '')}\n    {m.get('snippet', '')}"
        )
    listado = "\n".join(lineas) if lineas else "(no hay mails)"

    return f"""Te paso {len(mails)} mails relacionados a búsqueda laboral (metadata +
snippet, en español o inglés). Armá el seguimiento de postulaciones y devolvé
SOLO este JSON:

{SCHEMA_BUSQUEDA}

Reglas estrictas:
- Una entrada por postulación real (empresa + puesto). Máximo 15.
- Agrupá los mails de la misma búsqueda en una sola postulación (no repitas).
- Ignorá lo que NO sea búsqueda laboral (promos de empleo genéricas, alertas
  masivas de "nuevos trabajos para vos", newsletters). Solo lo que sea TU
  postulación concreta o contacto real de un recruiter.
- "estado":
    postulada           = te postulaste, sin respuesta todavía.
    respondieron        = te contestaron / avanzó el proceso.
    entrevista_agendada = hay una entrevista pactada (poné la fecha en proxima_fecha).
    rechazada           = te dijeron que no.
    oferta              = te hicieron una oferta.
    sin_respuesta       = pasó bastante y no hubo novedades.
- "fecha": del último contacto (YYYY-MM-DD) o null.
- "proxima_fecha": si hay entrevista o deadline futuro (YYYY-MM-DD), si no null.
- "pendiente": qué le falta HACER a la persona (responder, completar formulario,
  agendar, mandar algo). Máx 12 palabras. "" si no hay nada pendiente.
- "detalle": resumen de la situación, máx 12 palabras, castellano rioplatense.
- "ref": el número [n] del mail más relevante de esa postulación (el más
  reciente). Es obligatorio.

Mails:
{listado}
"""


def _completar(system, prompt):
    """Llama a Claude una vez y devuelve el texto de la respuesta."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ClaudeConfigError(
            "Falta ANTHROPIC_API_KEY. Creá un .env con tu API key (ver README)."
        )

    client = anthropic.Anthropic(api_key=api_key)
    respuesta = client.messages.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        thinking={"type": "disabled"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        bloque.text for bloque in respuesta.content if bloque.type == "text"
    )


class ClaudeConfigError(Exception):
    """Falta configuración para usar Claude (p. ej. ANTHROPIC_API_KEY)."""


def analizar_mails(mails):
    """Triage general. Devuelve el dict del schema (ver SCHEMA_EJEMPLO)."""
    return parse_json_safe(_completar(SYSTEM_PROMPT, _armar_prompt(mails)))


def analizar_busqueda_laboral(mails):
    """Seguimiento de postulaciones. Devuelve el dict del schema (SCHEMA_BUSQUEDA)."""
    return parse_json_safe(
        _completar(SYSTEM_PROMPT_BUSQUEDA, _armar_prompt_busqueda(mails))
    )
