"""
recordatorios.py — Recordatorios fijos mensuales (alquiler, agua, luz, gas, ADT...).

Los carga la persona a mano y se repiten todos los meses. No dependen del
correo. Se guardan en recordatorios.json (sin base de datos).

Cada recordatorio: {id, concepto, dia (1-31 del mes), monto (texto libre)}.
Al listar, se calcula "proxima" (la próxima fecha de vencimiento como
YYYY-MM-DD) para que el front muestre "vence en X días" igual que todo lo demás.
"""

import os
import json
import calendar
from datetime import date

import comprobantes

ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordatorios.json")


class RecordatorioInvalido(Exception):
    """Datos de recordatorio inválidos (concepto vacío, día fuera de rango)."""


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


def proxima_fecha(dia, hoy=None):
    """Próxima ocurrencia del 'día del mes' (este mes si no pasó, si no el que
    viene), en formato YYYY-MM-DD. Ajusta meses cortos (ej: 31 -> 28/30)."""
    hoy = hoy or date.today()
    dia = max(1, min(31, int(dia)))

    def en_mes(anio, mes):
        ultimo = calendar.monthrange(anio, mes)[1]
        return date(anio, mes, min(dia, ultimo))

    candidata = en_mes(hoy.year, hoy.month)
    if candidata < hoy:
        mes = hoy.month + 1
        anio = hoy.year
        if mes > 12:
            mes, anio = 1, anio + 1
        candidata = en_mes(anio, mes)
    return candidata.isoformat()


def listar(hoy=None):
    """Devuelve los recordatorios con su 'proxima' fecha, ordenados por la más
    cercana."""
    items = _leer()
    for it in items:
        prox = proxima_fecha(it.get("dia", 1), hoy)
        it["proxima"] = prox
        it["mes"] = prox[:7]
        # Pagado si el mes de la próxima fecha (YYYY-MM) está en la lista de pagos.
        it["pagado"] = prox[:7] in (it.get("pagos") or [])
        it["comprobantes"] = comprobantes.listar(it.get("id", 0), prox[:7])
    items.sort(key=lambda it: it["proxima"])
    return items


def mes_actual(rid, hoy=None):
    """Mes (YYYY-MM) del ciclo vigente de un recordatorio."""
    for it in _leer():
        if it.get("id") == int(rid):
            return proxima_fecha(it.get("dia", 1), hoy)[:7]
    return proxima_fecha(1, hoy)[:7]


def historial(rid):
    """Historial mes a mes de un recordatorio: qué meses se pagaron y con qué
    comprobantes."""
    rid = int(rid)
    it = next((x for x in _leer() if x.get("id") == rid), None)
    if not it:
        return {"id": rid, "concepto": "", "meses": []}
    pagos = set(it.get("pagos") or [])
    comps = comprobantes.historial(rid)
    meses = sorted(pagos | set(comps.keys()), reverse=True)
    return {
        "id": rid,
        "concepto": it.get("concepto", ""),
        "meses": [
            {"mes": m, "pagado": m in pagos, "comprobantes": comps.get(m, [])}
            for m in meses
        ],
    }


def marcar_pagado(rid, pagado=True, hoy=None):
    """Marca (o desmarca) un recordatorio como pagado para el mes de su próxima
    fecha. Al mes siguiente vuelve a aparecer como pendiente automáticamente."""
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        return listar(hoy)
    items = _leer()
    for it in items:
        if it.get("id") == rid:
            mes = proxima_fecha(it.get("dia", 1), hoy)[:7]
            pagos = set(it.get("pagos") or [])
            if pagado:
                pagos.add(mes)
            else:
                pagos.discard(mes)
            it["pagos"] = sorted(pagos)
            break
    _guardar(items)
    return listar(hoy)


def importar(items):
    """Reemplaza los recordatorios con los de un archivo exportado (backup).
    Valida cada uno y reasigna ids."""
    if not isinstance(items, list):
        raise RecordatorioInvalido("El archivo no tiene el formato esperado.")
    nuevos = []
    for it in items:
        if not isinstance(it, dict):
            continue
        concepto = str(it.get("concepto", "")).strip()
        try:
            dia = int(it.get("dia"))
        except (TypeError, ValueError):
            continue
        if not concepto or not 1 <= dia <= 31:
            continue
        nuevos.append(
            {
                "id": len(nuevos) + 1,
                "concepto": concepto,
                "dia": dia,
                "monto": str(it.get("monto", "")).strip(),
            }
        )
    _guardar(nuevos)
    return listar()


def agregar(concepto, dia, monto=""):
    """Agrega un recordatorio y devuelve la lista actualizada."""
    concepto = (concepto or "").strip()
    if not concepto:
        raise RecordatorioInvalido("Poné un concepto (ej: Alquiler, Luz).")
    try:
        dia = int(dia)
    except (TypeError, ValueError):
        raise RecordatorioInvalido("El día tiene que ser un número del 1 al 31.")
    if not 1 <= dia <= 31:
        raise RecordatorioInvalido("El día tiene que estar entre 1 y 31.")

    items = _leer()
    nuevo_id = max((it.get("id", 0) for it in items), default=0) + 1
    items.append(
        {"id": nuevo_id, "concepto": concepto, "dia": dia, "monto": str(monto or "").strip()}
    )
    _guardar(items)
    return listar()


def editar(rid, concepto, dia, monto=""):
    """Edita concepto/día/monto de un recordatorio, conservando su historial de
    pagos. Devuelve la lista actualizada."""
    concepto = (concepto or "").strip()
    if not concepto:
        raise RecordatorioInvalido("Poné un concepto (ej: Alquiler, Luz).")
    try:
        dia = int(dia)
    except (TypeError, ValueError):
        raise RecordatorioInvalido("El día tiene que ser un número del 1 al 31.")
    if not 1 <= dia <= 31:
        raise RecordatorioInvalido("El día tiene que estar entre 1 y 31.")

    items = _leer()
    for it in items:
        if it.get("id") == int(rid):
            it["concepto"] = concepto
            it["dia"] = dia
            it["monto"] = str(monto or "").strip()
            break
    _guardar(items)
    return listar()


def borrar(rid):
    """Borra el recordatorio con ese id y devuelve la lista actualizada."""
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        return listar()
    items = [it for it in _leer() if it.get("id") != rid]
    _guardar(items)
    return listar()
