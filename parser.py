"""
parser.py — Parseo tolerante de la respuesta JSON de Claude.

Claude a veces devuelve JSON truncado (se corta el max_tokens) o con detalles
menores (comas colgantes, fences de markdown). `parse_json_safe` intenta
recuperar la mayor cantidad posible sin explotar con un stack trace.

También incluye utilidades de fechas (`dias_restantes`) que se testean en
paralelo con la lógica del cliente, para que el front y el back coincidan.
"""

import json
from datetime import date


class RespuestaIncompletaError(Exception):
    """
    La respuesta de Claude vino tan cortada que no hay nada rescatable
    (se truncó antes del primer cierre de objeto/array fuera de strings).

    El endpoint la traduce a un mensaje amigable: nunca debe llegar como
    stack trace al usuario.
    """


def _sin_fences(texto: str) -> str:
    """Saca fences de markdown (```json ... ```) y recorta hasta el primer
    { o [ para tolerar prosa antes del JSON."""
    s = texto.strip()

    # Sacar fences ```json / ``` si el modelo envolvió la respuesta.
    if s.startswith("```"):
        primera_nl = s.find("\n")
        if primera_nl != -1:
            s = s[primera_nl + 1 :]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()

    # Recortar prosa previa: arrancar en el primer { o [.
    inicios = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if inicios:
        s = s[min(inicios) :]
    return s.strip()


def _quitar_comas_colgantes(s: str) -> str:
    """Elimina comas que quedan justo antes de un } o ] (una coma colgante),
    respetando el contenido de los strings (una coma dentro de una comilla
    no se toca)."""
    resultado = []
    in_string = False
    escape = False

    for i, ch in enumerate(s):
        if in_string:
            resultado.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            resultado.append(ch)
            continue

        if ch == ",":
            # Mirar el próximo carácter no-blanco: si cierra estructura,
            # la coma es colgante y la descartamos.
            j = i + 1
            while j < len(s) and s[j] in " \t\r\n":
                j += 1
            if j < len(s) and s[j] in "}]":
                continue  # descartar la coma
        resultado.append(ch)

    return "".join(resultado)


def parse_json_safe(texto):
    """
    Parsea `texto` como JSON siendo tolerante a truncado.

    Estrategia:
      1. Intento directo con json.loads.
      2. Si falla: recorto hasta el último cierre de objeto/array VÁLIDO
         (fuera de strings, trackeando estado in-string y escapes),
         balanceo los brackets que quedaron abiertos, limpio comas
         colgantes y reintento.
      3. Si no hay ningún cierre válido para rescatar, levanto
         RespuestaIncompletaError.

    Devuelve el objeto parseado (dict o list).
    """
    if texto is None or not str(texto).strip():
        raise RespuestaIncompletaError("La respuesta vino vacía.")

    s = _sin_fences(str(texto))
    if not s:
        raise RespuestaIncompletaError("No se encontró JSON en la respuesta.")

    # 1) Intento directo.
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 2) Escaneo para encontrar el último cierre válido fuera de strings
    #    y el estado de la pila de brackets en ese punto.
    stack = []              # closers pendientes en orden de apertura
    in_string = False
    escape = False
    ultimo_cierre = -1
    stack_en_cierre = None

    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack:
                stack.pop()
            ultimo_cierre = i
            stack_en_cierre = list(stack)

    # 3) Sin ningún cierre válido: no hay nada que rescatar.
    if ultimo_cierre == -1:
        raise RespuestaIncompletaError(
            "La respuesta vino incompleta (sin ninguna estructura cerrada)."
        )

    candidato = s[: ultimo_cierre + 1]

    # Balancear: cerrar los brackets que quedaron abiertos, en orden inverso
    # al de apertura (se cierra primero el último que se abrió).
    if stack_en_cierre:
        candidato += "".join(reversed(stack_en_cierre))

    candidato = _quitar_comas_colgantes(candidato)

    try:
        return json.loads(candidato)
    except json.JSONDecodeError as e:
        raise RespuestaIncompletaError(
            "No se pudo reparar la respuesta truncada."
        ) from e


def dias_restantes(fecha_iso, hoy: date):
    """
    Días entre `hoy` y `fecha_iso` ('YYYY-MM-DD').

      - hoy         -> 0
      - mañana      -> 1
      - pasado      -> 2
      - ayer/vencido-> negativo
      - None/inválida -> None (se trata como "sin fecha")

    Espeja la lógica del cliente (static/index.html) para mantener paridad.
    """
    if not fecha_iso:
        return None
    try:
        d = date.fromisoformat(str(fecha_iso))
    except (ValueError, TypeError):
        return None
    return (d - hoy).days
