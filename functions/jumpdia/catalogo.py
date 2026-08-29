"""Catálogo canónico del informe DIA 4° básico · JUMP Math.

Nombres de ejes y de unidades JUMP fijados por la guía de desarrollador (§4).
El orden de `EJES` y de `UNIDADES_JUMP` es normativo: `D.ejes`, `D.ejeProm`,
`D.ejeQC` y `D.coverage` se emiten en este orden.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Ejes temáticos -------------------------------------------------------

EJES: tuple[str, ...] = (
    "Números y operaciones",
    "Patrones y álgebra",
    "Geometría",
    "Medición",
    "Datos y probabilidades",
)

#: Clave corta de cada eje en `D.students[]` (mismo orden que `EJES`).
EJE_CLAVES: tuple[str, ...] = ("nyo", "pa", "geo", "med", "dyp")

#: Formas alternativas encontradas en los informes oficiales → eje canónico.
ALIAS_EJES: dict[str, str] = {
    "numeros y operaciones": EJES[0],
    "numero y operaciones": EJES[0],
    "numeros": EJES[0],
    "patrones y algebra": EJES[1],
    "patrones": EJES[1],
    "algebra": EJES[1],
    "geometria": EJES[2],
    "medicion": EJES[3],
    "datos y probabilidades": EJES[4],
    "datos y azar": EJES[4],
    "datos": EJES[4],
}


#: Tipos de ítem del DIA. El informe los imprime tal cual, con tilde.
TIPOS_ITEM: tuple[str, ...] = ("alternativas", "completación", "desarrollo")


# --- Unidades JUMP Math ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnidadJump:
    """Una unidad del texto JUMP Math de 4° básico."""

    tomo: str  # "4.1" | "4.2"
    u: str  # "U1" … "U8"
    label: str  # nombre original de la unidad

    @property
    def clave(self) -> str:
        """Identificador estable, p. ej. ``"4.1/U2"``."""
        return f"{self.tomo}/{self.u}"


#: Unidades en secuencia curricular. Los `label` son los nombres originales
#: exigidos por la guía (§4, regla "Nombres de unidades JUMP").
UNIDADES_JUMP: tuple[UnidadJump, ...] = (
    UnidadJump("4.1", "U1", "Series"),
    UnidadJump("4.1", "U2", "Valor posicional, sumas y restas"),
    UnidadJump("4.1", "U3", "Redondear"),
    UnidadJump("4.1", "U4", "Multiplicar"),
    UnidadJump("4.1", "U5", "Dividir"),
    UnidadJump("4.1", "U6", "Unidades métricas y tiempo"),
    UnidadJump("4.2", "U1", "Figuras"),
    UnidadJump("4.2", "U2", "Hallar el resto"),
    UnidadJump("4.2", "U3", "Problemas"),
    UnidadJump("4.2", "U4", "Fracciones"),
    UnidadJump("4.2", "U5", "Decimales"),
    UnidadJump("4.2", "U6", "Área y volumen"),
    UnidadJump("4.2", "U7", "Ángulos y coordenadas"),
    UnidadJump("4.2", "U8", "Diagramas"),
)

POR_CLAVE: dict[str, UnidadJump] = {u.clave: u for u in UNIDADES_JUMP}


def unidad(clave: str) -> UnidadJump:
    """Resuelve ``"4.1/U2"``, ``"4.1 U2"`` o ``"4.1·U2"`` a una `UnidadJump`."""
    norm = clave.replace("·", "/").replace(" ", "/").replace("//", "/").strip()
    if norm in POR_CLAVE:
        return POR_CLAVE[norm]
    raise KeyError(f"unidad JUMP desconocida: {clave!r}")


def unidad_por_nombre(numero: int, etiqueta: str) -> UnidadJump | None:
    """Resuelve una unidad por su número y su nombre, tolerando erratas.

    El número solo no basta: «Unidad 1» es *Series* en el Tomo 4.1 y *Figuras*
    en el 4.2. Es el nombre el que decide el tomo. Se compara por similitud
    porque las planillas de los colegios traen erratas — «Undades métricas y
    tiempo» es un caso real— que una comparación exacta descartaría.
    """
    from difflib import SequenceMatcher

    from .normalizacion import clave as _clave

    candidatas = [u for u in UNIDADES_JUMP if u.u == f"U{numero}"]
    if not candidatas:
        return None
    if len(candidatas) == 1 and not _clave(etiqueta):
        return candidatas[0]

    objetivo = _clave(etiqueta)
    mejor, puntaje = None, 0.0
    for unidad in candidatas:
        similitud = SequenceMatcher(None, objetivo, _clave(unidad.label)).ratio()
        if similitud > puntaje:
            mejor, puntaje = unidad, similitud
    return mejor if puntaje >= 0.6 else None


def indice_eje(nombre: str) -> int:
    """Índice canónico del eje, tolerando tildes/mayúsculas/variantes."""
    from .normalizacion import sin_tildes

    plano = sin_tildes(nombre).lower().strip()
    for i, eje in enumerate(EJES):
        if sin_tildes(eje).lower() == plano:
            return i
    if plano in ALIAS_EJES:
        return EJES.index(ALIAS_EJES[plano])
    raise KeyError(f"eje desconocido: {nombre!r}")
