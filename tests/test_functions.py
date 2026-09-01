"""Comprobaciones de la capa de Cloud Functions.

No levantan el emulador: verifican que el módulo carga, que declara las
funciones esperadas y que las validaciones de entrada rechazan lo que deben.
Así un error de dedo en `main.py` se ve en CI y no en el despliegue.
"""

from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture(scope="module")
def main(monkeypatch_module):
    """Carga `functions/main.py` fuera del runtime de Firebase.

    En producción el CLI de Firebase inyecta `FIREBASE_CONFIG` y las
    credenciales de servicio; aquí se simulan las dos cosas, porque el
    decorador de Storage exige conocer el bucket en tiempo de importación.
    """
    import json

    import firebase_admin

    monkeypatch_module.setenv(
        "FIREBASE_CONFIG",
        json.dumps(
            {"projectId": "jumpmathv2", "storageBucket": "jumpmathv2.firebasestorage.app"}
        ),
    )
    monkeypatch_module.setenv("GCLOUD_PROJECT", "jumpmathv2")
    monkeypatch_module.setattr(firebase_admin, "initialize_app", lambda *_a, **_k: None)
    sys.modules.pop("main", None)
    import main as modulo

    return modulo


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_el_modulo_carga_y_declara_las_funciones(main):
    for nombre in ("generar_informe", "informe", "obtener_informe", "listar_informes"):
        assert hasattr(main, nombre), f"falta la función {nombre}"


def test_no_hay_disparador_de_storage(main):
    """Se retiró a propósito.

    `registrar_subida` anotaba cada archivo subido en Firestore para que la
    interfaz marcara «Cargado», pero la interfaz nunca lo leyó: marca la subida
    cuando `uploadBytes` resuelve. Y desde que la carpeta de subida es un lote
    al azar, escribía documentos basura `cursos/{uid}_{lote}`. Era además la
    única función con disparador de Eventarc, la que ató la región al bucket y
    la que más costó desplegar.
    """
    assert not hasattr(main, "registrar_subida")
    assert "storage_fn" not in dir(main)


def test_ranuras_coinciden_con_la_guia(main):
    assert main.RANURAS == {
        "dia_oficial": True,
        "estudiantes": True,
        "recomendaciones": True,
        "seguimiento": True,
        "plan_anual": False,
    }


@pytest.mark.parametrize("valido", ["1886-4a", "12345-8h", "100-1a"])
def test_curso_id_valido(main, valido):
    assert main._exigir_curso_id({"cursoId": valido}) == valido


@pytest.mark.parametrize("lote", ["c79cd375b8364041a8ee1a259c1e2c2e", "abcdefgh", "a" * 40])
def test_lote_valido(main, lote):
    assert main._RE_LOTE.match(lote)


@pytest.mark.parametrize(
    "lote", ["", "corto", "a" * 41, "1886-4a", "../x", "ABCDEFGH", "con espacio"]
)
def test_lote_invalido(main, lote):
    """El lote es un segmento de ruta en Storage: sin travesía ni mayúsculas."""
    assert not main._RE_LOTE.match(lote)


@pytest.mark.parametrize(
    "invalido",
    ["", "1886", "4a", "1886-4", "1886-4z", "../../etc/passwd", "1886-4a/../otro", "abcd-4a"],
)
def test_curso_id_invalido_es_rechazado(main, invalido):
    """El id se usa para armar rutas de Storage: no puede admitir travesía."""
    from firebase_functions import https_fn

    with pytest.raises(https_fn.HttpsError):
        main._exigir_curso_id({"cursoId": invalido})


def test_sin_sesion_no_hay_ingesta(main):
    from firebase_functions import https_fn

    peticion = types.SimpleNamespace(auth=None, data={})
    with pytest.raises(https_fn.HttpsError):
        main._exigir_sesion(peticion)


def test_ruta_de_storage_queda_bajo_el_uid(main):
    assert main._ruta("uid123", "1886-4a", "dia_oficial") == "cursos/uid123/1886-4a/dia_oficial"


# --- Coherencia entre el cliente y el backend ----------------------------


def _config_del_cliente() -> dict[str, str]:
    """Lee los literales de `public/firebase-config.js` sin ejecutar JS."""
    import re

    from tests.conftest import RAIZ

    fuente = (RAIZ / "public" / "firebase-config.js").read_text(encoding="utf-8")
    # Capta tanto las propiedades del objeto (`projectId: "…"`) como las
    # constantes exportadas sueltas (`export const region = "…"`).
    return dict(re.findall(r'(\w+)\s*[:=]\s*"([^"]+)"', fuente))


def test_la_region_es_la_misma_en_los_tres_archivos(main):
    """Un desajuste de región no se ve al desplegar: falla con NOT_FOUND en uso.

    Y el `rewrite` de Hosting apunta a la región de la función: si se separa,
    `/api/informe` devuelve 404 aunque la función esté desplegada y sana.
    """
    import json

    from tests.conftest import RAIZ

    config = json.loads((RAIZ / "firebase.json").read_text(encoding="utf-8"))
    rewrite = config["hosting"]["rewrites"][0]["region"]

    assert _config_del_cliente().get("region") == main.REGION
    assert rewrite == main.REGION


def test_el_proyecto_del_cliente_coincide_con_firebaserc():
    import json

    from tests.conftest import RAIZ

    alias = json.loads((RAIZ / ".firebaserc").read_text(encoding="utf-8"))
    assert alias["projects"]["default"] == _config_del_cliente()["projectId"]


# --- Lista de acceso -----------------------------------------------------


@pytest.mark.parametrize(
    "correo, permitido",
    [
        ("javier.neo@gmail.com", True),
        ("JAVIER.NEO@Gmail.com", True),
        ("ana@jumpmath.cl", True),
        ("ana@JUMPMATH.CL", True),
        ("  ana@jumpmath.cl  ", True),
        ("otro@gmail.com", False),
        # Sufijo pegado: el dominio real es evil.cl, no jumpmath.cl.
        ("javier.neo@gmail.com.evil.cl", False),
        ("alguien@jumpmath.cl.evil.cl", False),
        # Subdominio: no es el dominio autorizado.
        ("alguien@sub.jumpmath.cl", False),
        ("sinarroba", False),
        ("a@b@jumpmath.cl", False),
        ("", False),
        (None, False),
    ],
)
def test_correo_autorizado(main, correo, permitido):
    assert main.correo_autorizado(correo) is permitido


def _autorizados_en_reglas(texto: str) -> tuple[set[str], set[str]]:
    """Correos y dominios de un archivo `.rules`.

    Se leen de las dos formas concretas en que las reglas los expresan, y no
    con una búsqueda laxa de correos: el dominio del propio correo autorizado
    (`gmail.com`) no es un dominio autorizado, y confundirlos haría pasar una
    regla que abriera todo Gmail.
    """
    import re

    correos: set[str] = set()
    for lista in re.findall(r"email\.lower\(\) in \[([^\]]*)\]", texto):
        correos |= set(re.findall(r"'([^']+)'", lista))
    dominios = {
        f"{a}.{b}"
        for a, b in re.findall(r"matches\('\.\*@([\w-]+)\[\.\]([\w-]+)'\)", texto)
    }
    return correos, dominios


def _autorizados_en_cliente(texto: str) -> tuple[set[str], set[str]]:
    """Correos y dominios de las dos constantes de `public/app.js`."""
    import re

    def lista(nombre: str) -> set[str]:
        m = re.search(rf"const {nombre} = \[([^\]]*)\]", texto)
        return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()

    return lista("CORREOS_AUTORIZADOS"), lista("DOMINIOS_AUTORIZADOS")


def test_la_lista_de_acceso_es_la_misma_en_los_cuatro_archivos(main):
    """Cuatro copias de la misma lista: dos reglas, las funciones y el cliente.

    Cada servicio evalúa las suyas, así que la duplicación es inevitable; lo
    que no puede pasar es que se separen. Una regla más laxa que las funciones
    abre la base de datos, y una más estricta deja fuera a alguien a quien la
    interfaz sí deja entrar.
    """
    from tests.conftest import RAIZ

    esperado = (set(main.CORREOS_AUTORIZADOS), set(main.DOMINIOS_AUTORIZADOS))
    assert esperado == ({"javier.neo@gmail.com"}, {"jumpmath.cl"})

    for archivo, extraer in (
        ("firestore.rules", _autorizados_en_reglas),
        ("storage.rules", _autorizados_en_reglas),
        ("public/app.js", _autorizados_en_cliente),
    ):
        obtenido = extraer((RAIZ / archivo).read_text(encoding="utf-8"))
        assert obtenido == esperado, f"{archivo} no coincide: {obtenido} != {esperado}"


def test_las_reglas_exigen_correo_verificado():
    """Sin `email_verified`, un proveedor que no valide el correo dejaría entrar
    a quien declarase uno ajeno."""
    from tests.conftest import RAIZ

    for archivo in ("firestore.rules", "storage.rules"):
        texto = (RAIZ / archivo).read_text(encoding="utf-8")
        assert "email_verified" in texto, f"{archivo} no comprueba el correo verificado"


def test_el_informe_no_acepta_el_uid_por_la_url(main):
    """El informe lleva datos personales: el `uid` sale del token, no de la URL."""
    import inspect

    fuente = inspect.getsource(main)
    assert 'args.get("uid"' not in fuente
    assert "_uid_del_portador" in fuente
