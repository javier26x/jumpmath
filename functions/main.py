"""Cloud Functions for Firebase · backend del Informe DIA (JUMP Math).

Flujo completo del Paso 1 de la guía:

1. El docente sube los archivos a Cloud Storage bajo su propio `uid`.
2. `generar_informe` (callable) ejecuta la ingesta y guarda el `D` resultante
   en Firestore.
3. `informe` (HTTP) sirve el HTML autocontenido con ese `D` ya inyectado.
4. `exportar_pdf` deja la exportación en manos del navegador (guía §6).

Las funciones son de 2ª generación y viven en `us-east1`, la región del bucket
de Storage del proyecto. No es una preferencia: una función que escucha un
bucket tiene que estar en su misma región, y la ubicación por defecto de un
proyecto Firebase se fija al crearlo y no se puede cambiar. Además la ingesta
descarga de ese bucket varios megas por curso, así que compartir región le
ahorra latencia y tráfico de salida; frente a eso, el viaje extra de la
petición del docente es despreciable.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import re
from typing import Any

from firebase_admin import firestore, initialize_app, storage
from firebase_functions import https_fn, options, storage_fn
from jumpdia import Archivo, Entrada, ErrorIngesta, ensamblar, inyectar_D

#: Debe coincidir con la región del bucket y con `firebase.json` y
#: `firebase-config.js`. Hay un test que lo comprueba.
REGION = "us-east1"
options.set_global_options(region=REGION, memory=options.MemoryOption.MB_512)

app = initialize_app()

#: Bucket de Storage. Vacío significa el bucket por omisión del proyecto, que
#: es lo normal; la variable sólo existe para apuntar a otro en pruebas.
#:
#: Se lee del entorno y no con `params.StringParam`: un parámetro declarado
#: hace que el CLI pregunte su valor en cada despliegue y lo guarde en un
#: `.env` por proyecto, ceremonia que aquí no aporta nada.
BUCKET = os.environ.get("JUMPDIA_BUCKET", "")

#: Los cuatro archivos obligatorios más el plan anual opcional (guía §4).
RANURAS: dict[str, bool] = {
    "dia_oficial": True,
    "estudiantes": True,
    "recomendaciones": True,
    "seguimiento": True,
    "plan_anual": False,
}

#: `cursos/{cursoId}` — el id lo arma el cliente como `rbd-curso`.
_RE_CURSO_ID = re.compile(r"^[0-9]{3,7}-[0-9]{1,2}[a-h]$")

_PLANTILLA = pathlib.Path(__file__).parent / "plantilla" / "index.html"


# --- Utilidades -----------------------------------------------------------


def _bucket():
    return storage.bucket(BUCKET or None)


def _ruta(uid: str, curso_id: str, ranura: str) -> str:
    return f"cursos/{uid}/{curso_id}/{ranura}"


def _exigir_sesion(req: https_fn.CallableRequest) -> str:
    """Devuelve el `uid` del docente o rechaza la llamada."""
    if req.auth is None or not req.auth.uid:
        raise https_fn.HttpsError(
            https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            "Inicie sesión para generar el informe.",
        )
    return req.auth.uid


def _exigir_curso_id(datos: dict[str, Any]) -> str:
    curso_id = str(datos.get("cursoId", "")).strip().lower()
    if not _RE_CURSO_ID.match(curso_id):
        raise https_fn.HttpsError(
            https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            "cursoId debe tener la forma «RBD-curso», por ejemplo «1886-4a».",
        )
    return curso_id


def _descargar(uid: str, curso_id: str, ranura: str) -> Archivo | None:
    """Baja el archivo de una ranura; `None` si no se subió."""
    bucket = _bucket()
    prefijo = _ruta(uid, curso_id, ranura)
    blobs = sorted(
        bucket.list_blobs(prefix=prefijo + "/"),
        key=lambda b: b.updated or dt.datetime.min,
        reverse=True,
    )
    if not blobs:
        return None
    blob = blobs[0]
    return Archivo(nombre=blob.name.rsplit("/", 1)[-1], datos=blob.download_as_bytes())


# --- 1 · Registro de subidas ---------------------------------------------


@storage_fn.on_object_finalized()
def registrar_subida(evento: storage_fn.CloudEvent[storage_fn.StorageObjectData]) -> None:
    """Anota en Firestore cada archivo que llega, para pintar el Paso 1.

    Que la interfaz marque «Cargado» a partir de un documento de Firestore y
    no de un evento del navegador evita el caso en que la subida falló a
    medias y el botón «Generar informe» quedó habilitado igual.
    """
    partes = (evento.data.name or "").split("/")
    if len(partes) < 4 or partes[0] != "cursos":
        return
    _, uid, curso_id, ranura = partes[:4]
    if ranura not in RANURAS:
        return

    cliente = firestore.client()
    cliente.document(f"cursos/{uid}_{curso_id}").set(
        {
            "uid": uid,
            "cursoId": curso_id,
            "archivos": {
                ranura: {
                    "nombre": partes[-1],
                    "tamano": evento.data.size,
                    "contentType": evento.data.content_type,
                    "actualizado": firestore.SERVER_TIMESTAMP,
                }
            },
        },
        merge=True,
    )


# --- 2 · Ingesta ----------------------------------------------------------


@https_fn.on_call(timeout_sec=300, memory=options.MemoryOption.GB_1)
def generar_informe(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Ejecuta la ingesta de §4 y guarda el `D` del curso en Firestore.

    Devuelve el `D` junto con los avisos del pipeline: no son errores, son las
    decisiones que hubo que tomar por datos ausentes o ambiguos, y el docente
    debe poder verlas antes de dar el informe por bueno.
    """
    uid = _exigir_sesion(req)
    curso_id = _exigir_curso_id(req.data or {})
    estricto = bool((req.data or {}).get("estricto", True))

    archivos = {ranura: _descargar(uid, curso_id, ranura) for ranura in RANURAS}
    faltan = [r for r, obligatorio in RANURAS.items() if obligatorio and archivos[r] is None]
    if faltan:
        raise https_fn.HttpsError(
            https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            "Faltan archivos obligatorios: " + ", ".join(faltan),
        )

    try:
        salida = ensamblar(
            Entrada(
                dia_oficial=archivos["dia_oficial"],
                estudiantes=archivos["estudiantes"],
                recomendaciones=archivos["recomendaciones"],
                seguimiento=archivos["seguimiento"],
                plan_anual=archivos["plan_anual"],
            ),
            estricto=estricto,
        )
    except ErrorIngesta as exc:
        # El detalle es accionable (qué columna falta, en qué archivo), así que
        # se devuelve al cliente en vez de esconderlo en los logs.
        raise https_fn.HttpsError(
            https_fn.FunctionsErrorCode.INVALID_ARGUMENT, str(exc)
        ) from exc

    cliente = firestore.client()
    doc = cliente.document(f"cursos/{uid}_{curso_id}")
    doc.set(
        {
            "uid": uid,
            "cursoId": curso_id,
            "D": salida.D,
            "avisos": salida.avisos,
            "generado": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    doc.collection("versiones").add(
        {"D": salida.D, "avisos": salida.avisos, "generado": firestore.SERVER_TIMESTAMP}
    )

    return {"D": salida.D, "avisos": salida.avisos, "cursoId": curso_id}


# --- 3 · Entrega del informe ---------------------------------------------


@https_fn.on_request(cors=options.CorsOptions(cors_origins=["*"], cors_methods=["get"]))
def informe(req: https_fn.Request) -> https_fn.Response:
    """Sirve el HTML autocontenido con el `D` del curso ya inyectado.

    Es la forma que describe la guía §3: «el backend produce ese `D` y sirve
    el HTML». No hay build ni hidratación en el cliente.
    """
    uid = req.args.get("uid", "")
    curso_id = req.args.get("curso", "").lower()
    if not uid or not _RE_CURSO_ID.match(curso_id):
        return https_fn.Response("Faltan los parámetros uid y curso.", status=400)

    doc = firestore.client().document(f"cursos/{uid}_{curso_id}").get()
    if not doc.exists or "D" not in (doc.to_dict() or {}):
        return https_fn.Response("Informe no generado para ese curso.", status=404)

    html = inyectar_D(_PLANTILLA.read_text(encoding="utf-8"), doc.to_dict()["D"])
    return https_fn.Response(
        html,
        status=200,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            # El informe cambia sólo cuando se regenera: se revalida siempre.
            "Cache-Control": "private, no-cache",
        },
    )


@https_fn.on_call()
def obtener_informe(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Devuelve el `D` guardado del curso, para repintar sin reprocesar."""
    uid = _exigir_sesion(req)
    curso_id = _exigir_curso_id(req.data or {})
    doc = firestore.client().document(f"cursos/{uid}_{curso_id}").get()
    if not doc.exists:
        raise https_fn.HttpsError(
            https_fn.FunctionsErrorCode.NOT_FOUND, "Ese curso aún no tiene informe."
        )
    datos = doc.to_dict() or {}
    return {"D": datos.get("D"), "avisos": datos.get("avisos", [])}
