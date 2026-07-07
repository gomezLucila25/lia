"""Tests del cálculo de días restantes (paridad con la lógica del cliente)."""

from datetime import date

from parser import dias_restantes


HOY = date(2026, 7, 7)


def test_hoy():
    assert dias_restantes("2026-07-07", HOY) == 0


def test_manana():
    assert dias_restantes("2026-07-08", HOY) == 1


def test_pasado_manana():
    assert dias_restantes("2026-07-09", HOY) == 2


def test_vencido():
    assert dias_restantes("2026-07-04", HOY) == -3


def test_null():
    assert dias_restantes(None, HOY) is None


def test_fecha_invalida_es_none():
    assert dias_restantes("no-es-fecha", HOY) is None
    assert dias_restantes("", HOY) is None
