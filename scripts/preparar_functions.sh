#!/usr/bin/env bash
# Prepara el entorno virtual que el CLI de Firebase necesita para desplegar.
#
# Antes de subir nada, el CLI importa el código de las funciones para descubrir
# cuáles hay, y para eso exige un `functions/venv` ya creado. Sin él aborta con
# «Missing virtual environment at venv directory». Ese entorno es sólo local:
# el runtime de producción lo construye Google a partir de requirements.txt.
#
# Se ejecuta desde el hook `predeploy` de firebase.json, así que un despliegue
# en una máquina nueva funciona sin pasos manuales.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destino="$raiz/functions/venv"
requisitos="$raiz/functions/requirements.txt"

# El intérprete se deduce del runtime declarado, para que ambos no se separen.
runtime="$(python3 -c "
import json, pathlib
config = json.loads(pathlib.Path('$raiz/firebase.json').read_text())
print(config['functions'][0]['runtime'])
")"
version="${runtime#python}"
preferido="python${version:0:1}.${version:1}"

if command -v "$preferido" >/dev/null 2>&1; then
  interprete="$preferido"
else
  interprete="python3"
  echo "Aviso: no hay $preferido en esta máquina; se usa $(python3 -V) para el" >&2
  echo "       descubrimiento local. El runtime desplegado sigue siendo $runtime." >&2
fi

if [[ ! -x "$destino/bin/python" ]]; then
  echo "Creando el entorno virtual de las funciones con $interprete…"
  "$interprete" -m venv "$destino"
fi

# Se reinstala sólo cuando cambian las dependencias: en un despliegue normal
# esto es una comparación de hashes, no una instalación.
sello="$destino/.requirements.sha256"
actual="$(sha256sum "$requisitos" | cut -d' ' -f1)"
if [[ "$(cat "$sello" 2>/dev/null || true)" != "$actual" ]]; then
  echo "Instalando las dependencias de las funciones…"
  "$destino/bin/pip" install --quiet --upgrade pip
  "$destino/bin/pip" install --quiet -r "$requisitos"
  echo "$actual" > "$sello"
fi

echo "Entorno de funciones listo -> functions/venv"
