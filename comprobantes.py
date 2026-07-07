"""
comprobantes.py — Comprobantes de pago, organizados por mes.

Funciona como un "Drive" local. Cada comprobante se guarda en:
    comprobantes/<id-del-recordatorio>/<YYYY-MM>/<archivo>
Así queda atado al mes en que se pagó, y se puede armar el historial.

Todo local, gratis, sin nube.
"""

import os
import re

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comprobantes")


def _mes_seguro(mes):
    m = str(mes or "")
    return m if re.fullmatch(r"\d{4}-\d{2}", m) else "sin-mes"


def _nombre_seguro(nombre):
    """Sanea el nombre de archivo: sin rutas, sin caracteres raros, sin
    traversal (..)."""
    nombre = os.path.basename(nombre or "")
    nombre = re.sub(r"[^A-Za-z0-9._ \-]", "_", nombre)
    if not nombre or nombre in (".", ".."):
        nombre = "comprobante"
    return nombre


def _dir(rid, mes):
    return os.path.join(BASE, str(int(rid)), _mes_seguro(mes))


def listar(rid, mes):
    """Nombres de comprobantes de un recordatorio en un mes dado."""
    d = _dir(rid, mes)
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)))


def guardar(rid, mes, nombre, contenido: bytes):
    """Guarda un comprobante para ese mes. Si el nombre existe, agrega (1), (2)..."""
    d = _dir(rid, mes)
    os.makedirs(d, exist_ok=True)
    nombre = _nombre_seguro(nombre)
    base, ext = os.path.splitext(nombre)
    destino = os.path.join(d, nombre)
    i = 1
    while os.path.exists(destino):
        destino = os.path.join(d, f"{base} ({i}){ext}")
        i += 1
    with open(destino, "wb") as f:
        f.write(contenido)
    return listar(rid, mes)


def ruta(rid, mes, nombre):
    """Ruta absoluta de un comprobante, validando que quede DENTRO de su
    carpeta (protección contra path traversal). None si no existe."""
    d = os.path.abspath(_dir(rid, mes))
    p = os.path.abspath(os.path.join(d, _nombre_seguro(nombre)))
    if os.path.commonpath([p, d]) != d:
        return None
    return p if os.path.isfile(p) else None


def borrar(rid, mes, nombre):
    """Borra un comprobante de un mes y devuelve la lista de ese mes."""
    p = ruta(rid, mes, nombre)
    if p and os.path.isfile(p):
        os.remove(p)
    return listar(rid, mes)


def historial(rid):
    """Todos los meses con comprobantes de un recordatorio: {mes: [archivos]}."""
    base = os.path.join(BASE, str(int(rid)))
    if not os.path.isdir(base):
        return {}
    salida = {}
    for mes in os.listdir(base):
        md = os.path.join(base, mes)
        if os.path.isdir(md):
            salida[mes] = sorted(
                f for f in os.listdir(md) if os.path.isfile(os.path.join(md, f))
            )
    return salida
