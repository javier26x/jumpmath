#!/usr/bin/env bash
# Copia la plantilla del informe dentro de functions/ antes de desplegar.
#
# El despliegue de Cloud Functions sólo empaqueta el directorio functions/, así
# que la función no puede leer ../public/. En vez de mantener dos copias en el
# repositorio —que se separarían a la primera edición— la copia se genera aquí
# y está en .gitignore. `public/index.html` es la única fuente.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
origen="$raiz/public/index.html"
destino="$raiz/functions/plantilla/index.html"

[[ -f "$origen" ]] || { echo "No existe $origen" >&2; exit 1; }
mkdir -p "$(dirname "$destino")"
cp "$origen" "$destino"
echo "Plantilla sincronizada -> functions/plantilla/index.html"
