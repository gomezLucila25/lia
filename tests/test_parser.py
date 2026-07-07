"""Tests de parse_json_safe: JSON sano, truncados varios, escapes y sin-JSON."""

import pytest

from parser import parse_json_safe, RespuestaIncompletaError


def test_json_sano():
    texto = '{"vencimientos": [{"titulo": "Luz", "monto": 100}], "ruido_count": 3}'
    data = parse_json_safe(texto)
    assert data["ruido_count"] == 3
    assert data["vencimientos"][0]["titulo"] == "Luz"


def test_json_con_fences_markdown():
    texto = '```json\n{"accion": [], "ruido_count": 0}\n```'
    data = parse_json_safe(texto)
    assert data["accion"] == []
    assert data["ruido_count"] == 0


def test_truncado_a_mitad_de_string():
    # Se corta dentro del string de "accion"; hay que rescatar "vencimientos".
    texto = (
        '{"vencimientos": [{"titulo": "Factura Edenor"}], '
        '"accion": [{"titulo": "Pagar la cuenta de luz que venc'
    )
    data = parse_json_safe(texto)
    assert data["vencimientos"][0]["titulo"] == "Factura Edenor"
    # La sección incompleta se descarta limpiamente.
    assert "accion" not in data or data["accion"] == []


def test_truncado_tras_coma():
    # Cierre válido y después una coma colgante por corte.
    texto = '{"vencimientos": [{"titulo": "ARBA"}],'
    data = parse_json_safe(texto)
    assert data["vencimientos"][0]["titulo"] == "ARBA"


def test_coma_colgante_antes_de_cierre():
    # Coma colgante emitida por el modelo, no por truncado.
    texto = '{"informativo": [1, 2, 3,]}'
    data = parse_json_safe(texto)
    assert data["informativo"] == [1, 2, 3]


def test_llaves_y_comillas_escapadas_dentro_de_strings():
    # Llaves, corchetes y comillas escapadas adentro de un string, truncado
    # justo después de un objeto completo. El reparador no se debe confundir
    # con las llaves de adentro del string.
    texto = (
        '{"vencimientos": [{"titulo": "Pago \\"especial\\" {con} [llaves]", '
        '"detalle": "vence, y \\\\ barra"}], "accion": [{"titulo": "otra co'
    )
    data = parse_json_safe(texto)
    v = data["vencimientos"][0]
    assert v["titulo"] == 'Pago "especial" {con} [llaves]'
    assert v["detalle"] == "vence, y \\ barra"


def test_respuesta_sin_json():
    with pytest.raises(RespuestaIncompletaError):
        parse_json_safe("Perdón, no puedo ayudarte con eso.")


def test_truncado_antes_del_primer_cierre():
    # Edge case: se corta antes de cualquier cierre fuera de strings.
    # No hay nada rescatable -> error amigable, nunca stack trace.
    texto = '{"vencimientos": [{"titulo": "algo que se cort'
    with pytest.raises(RespuestaIncompletaError):
        parse_json_safe(texto)


def test_vacio_y_none():
    with pytest.raises(RespuestaIncompletaError):
        parse_json_safe("")
    with pytest.raises(RespuestaIncompletaError):
        parse_json_safe(None)


def test_array_top_level_truncado():
    texto = '[{"a": 1}, {"b": 2}, {"c":'
    data = parse_json_safe(texto)
    assert data == [{"a": 1}, {"b": 2}]
