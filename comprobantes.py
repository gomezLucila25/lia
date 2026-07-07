"""
comprobantes.py — Comprobantes de pago adjuntos a cada recordatorio.

Funciona como un "Drive" local: subís el comprobante de un pago (PDF, foto, etc.)
y queda guardado en tu disco, dentro de comprobantes/<id-del-recordatorio>/.
Después lo podés abrir o borrar.

Todo local, gratis, sin nube.
"""

import os
import re

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comprobantes")


def _dir(rid):
    return os.path.join(BASE, str(int(rid)))


def _nombre_seguro(nombre):
    """Sanea el nombre de archivo: sin rutas, sin caracteres raros, sin
    traversal (..). Evita que un nombre malicioso escriba fuera de la carpeta."""
    nombre = os.path.basename(nombre or "")
    nombre = re.sub(r"[^A-Za-z0-9._ \-]", "_", nombre)
    if not nombre or nombre in (".", ".."):
        nombre = "comprobante"
    return nombre


def listar(rid):
    """Nombres de los comprobantes de un recordatorio (ordenados)."""
    d = _dir(rid)
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n)))


def guardar(rid, nombre, contenido: bytes):
    """Guarda un comprobante. Si el nombre ya existe, agrega (1), (2)..."""
    d = _dir(rid)
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
    return listar(rid)


def ruta(rid, nombre):
    """Ruta absoluta de un comprobante, validando que quede DENTRO de su
    carpeta (protección contra path traversal). None si no existe."""
    d = os.path.abspath(_dir(rid))
    p = os.path.abspath(os.path.join(d, _nombre_seguro(nombre)))
    if os.path.commonpath([p, d]) != d:
        return None
    return p if os.path.isfile(p) else None


def borrar(rid, nombre):
    """Borra un comprobante y devuelve la lista actualizada."""
    p = ruta(rid, nombre)
    if p and os.path.isfile(p):
        os.remove(p)
    return listar(rid)
