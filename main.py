"""
main.py — App FastAPI de LIA Mail Triage.

Endpoints:
  GET  /               -> sirve la página única (static/index.html).
  POST /api/analizar   -> triage general del correo (vencimientos, acción, ...).
  POST /api/busqueda   -> seguimiento de búsqueda laboral (postulaciones).

Corré con:  uvicorn main:app --reload
"""

import os
from datetime import date

from fastapi import FastAPI, UploadFile, File, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from parser import RespuestaIncompletaError, dias_restantes
from gmail_client import obtener_mails, obtener_mails_busqueda, GmailAuthError
import claude_client
import gemini_client
import recordatorios
import comprobantes
from claude_client import ClaudeConfigError
from gemini_client import GeminiConfigError
from recordatorios import RecordatorioInvalido

app = FastAPI(title="LIA Mail Triage")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(BASE_DIR, "static", "index.html")


def _backend():
    """
    Elige el 'cerebro' que clasifica (mismo módulo para ambos análisis):

      - LIA_IA=gemini  -> Gemini (capa GRATIS).
      - LIA_IA=claude  -> Claude (pago).
      - sin LIA_IA      -> si hay GEMINI_API_KEY usa Gemini (gratis); si no, Claude.
    """
    pref = os.getenv("LIA_IA", "").strip().lower()
    if pref == "gemini":
        return gemini_client
    if pref == "claude":
        return claude_client
    if os.getenv("GEMINI_API_KEY"):
        return gemini_client
    return claude_client


# --- Modo demo (GRATIS): con LIA_DEMO=1 NO se toca Gmail ni la IA, así que
# no se descuenta nada. Sirve para probar el dashboard sin gastar. ---
def _modo_demo():
    return os.getenv("LIA_DEMO", "").strip() not in ("", "0", "false", "False")


DEMO_DATA = {
    "vencimientos": [
        {"titulo": "Factura Edenor", "emisor": "Edenor", "fecha": "2026-07-02",
         "detalle": "venció, saldo pendiente de luz", "estado": "pendiente"},
        {"titulo": "Resumen Visa Galicia", "emisor": "Banco Galicia", "fecha": "2026-07-07",
         "detalle": "vence hoy, total a pagar $84.300", "estado": "pendiente"},
        {"titulo": "ABL 3ra cuota", "emisor": "AGIP", "fecha": "2026-07-08",
         "detalle": "impuesto municipal, vence mañana", "estado": "pendiente"},
        {"titulo": "Netflix", "emisor": "Netflix", "fecha": "2026-07-11",
         "detalle": "suscripción, débito automático", "estado": "debito_automatico"},
        {"titulo": "Alquiler julio", "emisor": "Inmobiliaria Sur", "fecha": "2026-07-05",
         "detalle": "ya transferido este mes", "estado": "pagado"},
        {"titulo": "Patente auto", "emisor": "ARBA", "fecha": None,
         "detalle": "sin fecha clara en el mail", "estado": "pendiente"},
    ],
    "accion": [
        {"titulo": "Confirmar turno médico", "emisor": "Swiss Medical",
         "detalle": "responder para reservar el turno"},
        {"titulo": "Firmar documento", "emisor": "DocuSign",
         "detalle": "pendiente tu firma electrónica"},
    ],
    "informativo": [
        {"titulo": "Estado del envío", "emisor": "Correo Argentino",
         "detalle": "paquete en camino, llega el jueves"},
    ],
    "ruido_count": 12,
    "ruido_ejemplos": [
        "50% OFF solo por hoy en Frávega",
        "Newsletter semanal de Medium",
        "Tu resumen de actividad de LinkedIn",
    ],
}

DEMO_BUSQUEDA = {
    "postulaciones": [
        {"empresa": "Mercado Libre", "puesto": "UX Writer Sr", "fecha": "2026-07-06",
         "estado": "entrevista_agendada", "pendiente": "preparar la entrevista técnica",
         "proxima_fecha": "2026-07-09", "detalle": "avanzaste a segunda ronda"},
        {"empresa": "Globant", "puesto": "Content Designer", "fecha": "2026-07-04",
         "estado": "respondieron", "pendiente": "responder disponibilidad horaria",
         "proxima_fecha": None, "detalle": "la recruiter te escribió, falta responder"},
        {"empresa": "Auth0", "puesto": "Technical Writer", "fecha": "2026-06-28",
         "estado": "rechazada", "pendiente": "",
         "proxima_fecha": None, "detalle": "no avanzaron con tu perfil"},
        {"empresa": "Ualá", "puesto": "Product Designer", "fecha": "2026-06-20",
         "estado": "sin_respuesta", "pendiente": "quizás hacer follow-up",
         "proxima_fecha": None, "detalle": "postulaste hace 2 semanas, sin novedades"},
        {"empresa": "Naranja X", "puesto": "Redactora UX", "fecha": "2026-07-01",
         "estado": "postulada", "pendiente": "completar formulario del portal",
         "proxima_fecha": None, "detalle": "postulación enviada, falta un formulario"},
    ],
}


@app.get("/")
def index():
    return FileResponse(INDEX_HTML)


def _merge_recordatorios(resultado):
    """Suma los recordatorios fijos a la lista de 'vencimientos' del triage,
    para verlos junto con los del correo. Crea una lista nueva (no muta el demo)."""
    extra = []
    for r in recordatorios.listar():
        detalle = r.get("monto") or f"todos los meses el día {r.get('dia')}"
        extra.append({
            "titulo": r.get("concepto", ""),
            "emisor": "Recordatorio fijo",
            "fecha": r.get("proxima"),
            "detalle": detalle,
            "estado": "pagado" if r.get("pagado") else "pendiente",
            "origen": "recordatorio",
        })
    resultado["vencimientos"] = list(resultado.get("vencimientos") or []) + extra


def _responder(traer_mails, analizar, demo, post=None):
    """Corre un flujo (traer mails -> analizar) y mapea toda falla a JSON
    amigable; nunca un stack trace al front. `post` transforma el resultado
    (p. ej. sumar recordatorios) antes de devolverlo."""
    try:
        if _modo_demo():
            resultado = dict(demo)
        else:
            mails = traer_mails()
            resultado = analizar(mails)
            # Mapa ref -> link de Gmail, para que el front abra el mail al clickear.
            resultado["_fuentes"] = [
                {"ref": i + 1, "link": m.get("link", "")}
                for i, m in enumerate(mails)
            ]
        if post:
            post(resultado)
        return JSONResponse(resultado)

    except GmailAuthError as e:
        return JSONResponse(
            {"error": f"Problema de acceso a Gmail: {e}"}, status_code=502
        )
    except (ClaudeConfigError, GeminiConfigError) as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except RespuestaIncompletaError:
        return JSONResponse(
            {"error": "La respuesta vino incompleta, reintentá."},
            status_code=502,
        )
    except Exception as e:  # red de seguridad: nunca stack trace crudo
        return JSONResponse(
            {"error": f"Algo salió mal, reintentá. ({type(e).__name__})"},
            status_code=500,
        )


@app.post("/api/analizar")
def analizar():
    """Triage general del correo + recordatorios fijos en 'vencimientos'."""
    return _responder(
        obtener_mails, _backend().analizar_mails, DEMO_DATA, post=_merge_recordatorios
    )


@app.post("/api/busqueda")
def busqueda():
    """Seguimiento de la búsqueda laboral (postulaciones)."""
    return _responder(
        obtener_mails_busqueda, _backend().analizar_busqueda_laboral, DEMO_BUSQUEDA
    )


# ---------------- Resumen (pantallazo de todo junto) ----------------

DEMO_RESUMEN = {
    "vencimientos_semana": [
        {"titulo": "Resumen Visa Galicia", "fecha": "2026-07-07", "dias": 0, "origen": "mail"},
        {"titulo": "ABL 3ra cuota", "fecha": "2026-07-08", "dias": 1, "origen": "mail"},
        {"titulo": "Alquiler", "fecha": "2026-07-09", "dias": 2, "origen": "recordatorio"},
    ],
    "entrevistas": [
        {"titulo": "UX Writer Sr — Mercado Libre", "fecha": "2026-07-09", "dias": 2},
    ],
    "pendientes_count": 2,
    "totales": {"vencimientos": 8, "entrevistas": 1},
}


def _armar_resumen(triage, jobs, recs, hoy):
    """Combina vencimientos del correo + recordatorios + postulaciones en un
    pantallazo de 'esta semana'."""
    venc = []
    for v in triage.get("vencimientos") or []:
        if v.get("estado") == "pagado":
            continue
        venc.append({
            "titulo": v.get("titulo"),
            "fecha": v.get("fecha"),
            "dias": dias_restantes(v.get("fecha"), hoy),
            "origen": "mail",
        })
    for r in recs:
        if r.get("pagado"):
            continue  # ya está pagado este mes, no lo mostramos como pendiente
        venc.append({
            "titulo": r.get("concepto"),
            "fecha": r.get("proxima"),
            "dias": dias_restantes(r.get("proxima"), hoy),
            "origen": "recordatorio",
        })
    # "Esta semana" = próximos 7 días (incluye lo ya vencido, dias < 0).
    semana = sorted(
        [x for x in venc if x["dias"] is not None and x["dias"] <= 7],
        key=lambda x: x["dias"],
    )

    entrevistas = []
    for p in jobs.get("postulaciones") or []:
        if p.get("estado") == "rechazada":
            continue
        if p.get("proxima_fecha") or p.get("estado") == "entrevista_agendada":
            entrevistas.append({
                "titulo": f"{p.get('puesto')} — {p.get('empresa')}",
                "fecha": p.get("proxima_fecha"),
                "dias": dias_restantes(p.get("proxima_fecha"), hoy),
            })
    entrevistas.sort(key=lambda x: (x["dias"] is None, x["dias"] or 0))

    pendientes = [p for p in (jobs.get("postulaciones") or []) if (p.get("pendiente") or "").strip()]

    return {
        "vencimientos_semana": semana,
        "entrevistas": entrevistas,
        "pendientes_count": len(pendientes),
        "totales": {"vencimientos": len(venc), "entrevistas": len(entrevistas)},
    }


class FollowupIn(BaseModel):
    empresa: str = ""
    puesto: str = ""
    detalle: str = ""


DEMO_FOLLOWUP = {
    "asunto": "Seguimiento — Content Designer",
    "cuerpo": (
        "Hola,\n\nTe escribo para retomar mi postulación al puesto de Content "
        "Designer. Sigo muy interesada en la posición y me encantaría saber si el "
        "proceso continúa o si necesitan algo más de mi parte.\n\n"
        "¡Gracias y quedo atenta!\n\nSaludos,\n[Tu nombre]"
    ),
}


@app.post("/api/followup")
def followup(post: FollowupIn):
    """Genera un borrador de mail de seguimiento para una postulación sin respuesta."""
    try:
        if _modo_demo():
            return JSONResponse(DEMO_FOLLOWUP)
        return JSONResponse(_backend().redactar_followup(post.model_dump()))
    except (ClaudeConfigError, GeminiConfigError) as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except RespuestaIncompletaError:
        return JSONResponse({"error": "La respuesta vino incompleta, reintentá."}, status_code=502)
    except Exception as e:
        return JSONResponse(
            {"error": f"Algo salió mal, reintentá. ({type(e).__name__})"}, status_code=500
        )


@app.post("/api/resumen")
def resumen():
    """Pantallazo combinado: vencimientos (correo + recordatorios) + búsqueda laboral."""
    try:
        if _modo_demo():
            return JSONResponse(DEMO_RESUMEN)
        backend = _backend()
        triage = backend.analizar_mails(obtener_mails())
        jobs = backend.analizar_busqueda_laboral(obtener_mails_busqueda())
        recs = recordatorios.listar()
        return JSONResponse(_armar_resumen(triage, jobs, recs, date.today()))
    except GmailAuthError as e:
        return JSONResponse({"error": f"Problema de acceso a Gmail: {e}"}, status_code=502)
    except (ClaudeConfigError, GeminiConfigError) as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except RespuestaIncompletaError:
        return JSONResponse({"error": "La respuesta vino incompleta, reintentá."}, status_code=502)
    except Exception as e:
        return JSONResponse(
            {"error": f"Algo salió mal, reintentá. ({type(e).__name__})"}, status_code=500
        )


# ---------------- Recordatorios fijos (local, sin correo ni IA) ----------------

class RecordatorioIn(BaseModel):
    concepto: str
    dia: int
    monto: str = ""


@app.get("/api/recordatorios")
def get_recordatorios():
    return JSONResponse({"recordatorios": recordatorios.listar()})


@app.post("/api/recordatorios")
def add_recordatorio(r: RecordatorioIn):
    try:
        lista = recordatorios.agregar(r.concepto, r.dia, r.monto)
        return JSONResponse({"recordatorios": lista})
    except RecordatorioInvalido as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.put("/api/recordatorios/{rid}")
def editar_recordatorio(rid: int, r: RecordatorioIn):
    """Edita un recordatorio (concepto/día/monto), conservando su historial."""
    try:
        return JSONResponse({"recordatorios": recordatorios.editar(rid, r.concepto, r.dia, r.monto)})
    except RecordatorioInvalido as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.delete("/api/recordatorios/{rid}")
def del_recordatorio(rid: int):
    return JSONResponse({"recordatorios": recordatorios.borrar(rid)})


class PagadoIn(BaseModel):
    pagado: bool = True


@app.post("/api/recordatorios/{rid}/pagado")
def marcar_pagado_endpoint(rid: int, body: PagadoIn):
    """Marca/desmarca un recordatorio como pagado este mes."""
    return JSONResponse({"recordatorios": recordatorios.marcar_pagado(rid, body.pagado)})


@app.post("/api/recordatorios/importar")
def importar_recordatorios(items: list = Body(...)):
    """Restaura recordatorios desde un archivo exportado (backup)."""
    try:
        return JSONResponse({"recordatorios": recordatorios.importar(items)})
    except RecordatorioInvalido as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ---------------- Comprobantes de pago (Drive local) ----------------

@app.post("/api/recordatorios/{rid}/comprobantes")
async def subir_comprobante(rid: int, archivo: UploadFile = File(...)):
    contenido = await archivo.read()
    mes = recordatorios.mes_actual(rid)
    lista = comprobantes.guardar(rid, mes, archivo.filename, contenido)
    # Subir el comprobante marca el recordatorio como pagado este mes.
    recordatorios.marcar_pagado(rid, True)
    return JSONResponse({"comprobantes": lista})


@app.get("/api/recordatorios/{rid}/comprobantes/{mes}/{nombre}")
def ver_comprobante(rid: int, mes: str, nombre: str):
    ruta = comprobantes.ruta(rid, mes, nombre)
    if not ruta:
        return JSONResponse({"error": "Comprobante no encontrado."}, status_code=404)
    return FileResponse(ruta, filename=nombre)


@app.delete("/api/recordatorios/{rid}/comprobantes/{mes}/{nombre}")
def borrar_comprobante(rid: int, mes: str, nombre: str):
    return JSONResponse({"comprobantes": comprobantes.borrar(rid, mes, nombre)})


@app.get("/api/recordatorios/{rid}/historial")
def historial_recordatorio(rid: int):
    """Historial mes a mes de un recordatorio (pagos + comprobantes)."""
    return JSONResponse(recordatorios.historial(rid))
