"""Errores del pipeline de ingesta."""

from __future__ import annotations


class ErrorIngesta(Exception):
    """Base de los errores del pipeline."""


class ErrorParseo(ErrorIngesta):
    """Un archivo de origen no pudo leerse con la estructura esperada."""

    def __init__(self, fuente: str, detalle: str) -> None:
        super().__init__(f"[{fuente}] {detalle}")
        self.fuente = fuente
        self.detalle = detalle


class ErrorValidacion(ErrorIngesta):
    """El objeto `D` armado no cumple el contrato de datos."""

    def __init__(self, problemas: list[str]) -> None:
        super().__init__("D no cumple el contrato:\n- " + "\n- ".join(problemas))
        self.problemas = problemas
