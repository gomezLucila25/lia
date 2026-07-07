"""
postulaciones.py — Postulaciones cargadas a mano.

Para las postulaciones que la IA no detecta en el correo (o que querés seguir
vos manualmente). Se guardan en postulaciones.json (sin base de datos) y se
muestran en su propia sección de Búsqueda laboral, con el mismo formato que
las detectadas por la IA.
"""

import os
import json

ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "postulaciones.json")

ESTADOS = {
    "postulada",
    "respondieron",
    "entrevista_agendada",
    "rechazada",
    "oferta",
    "sin_respuesta",
}


class PostulacionInvalida(Exception):
    """Datos de postulación inválidos (falta empresa y puesto)."""


def _leer():
    if not os.path.exists(ARCHIVO):
        return []
    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _guardar(items):
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def listar():
    """Postulaciones manuales, marcadas con origen='manual' para el front."""
    items = _leer()
    for it in items:
        it["origen"] = "manual"
    return items


def _validar(empresa, puesto, estado):
    empresa = (empresa or "").strip()
    puesto = (puesto or "").strip()
    if not empresa and not puesto:
        raise PostulacionInvalida("Poné al menos la empresa o el puesto.")
    estado = estado if estado in ESTADOS else "postulada"
    return empresa, puesto, estado


def agregar(empresa="", puesto="", estado="postulada", proxima_fecha="", pendiente="", detalle=""):
    empresa, puesto, estado = _validar(empresa, puesto, estado)
    items = _leer()
    nuevo_id = max((x.get("id", 0) for x in items), default=0) + 1
    items.append({
        "id": nuevo_id,
        "empresa": empresa,
        "puesto": puesto,
        "estado": estado,
        "proxima_fecha": (proxima_fecha or "").strip() or None,
        "pendiente": (pendiente or "").strip(),
        "detalle": (detalle or "").strip(),
        "fecha": None,
    })
    _guardar(items)
    return listar()


def editar(pid, empresa="", puesto="", estado="postulada", proxima_fecha="", pendiente="", detalle=""):
    empresa, puesto, estado = _validar(empresa, puesto, estado)
    items = _leer()
    for it in items:
        if it.get("id") == int(pid):
            it["empresa"] = empresa
            it["puesto"] = puesto
            it["estado"] = estado
            it["proxima_fecha"] = (proxima_fecha or "").strip() or None
            it["pendiente"] = (pendiente or "").strip()
            it["detalle"] = (detalle or "").strip()
            break
    _guardar(items)
    return listar()


def borrar(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return listar()
    _guardar([it for it in _leer() if it.get("id") != pid])
    return listar()
