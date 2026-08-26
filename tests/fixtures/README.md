# Fixtures

- **`D_4A_bulnes.json`** — el objeto `D` del informe 4° A ya publicado y
  revisado. Es la referencia dorada de los tests.
- **`dia_oficial_4A.pdf`, `estudiantes_4A.xlsx`, `recomendaciones_4B.xlsx`,
  `seguimiento_jump_4A.xlsx`** — archivos de entrada **sintéticos**, generados
  por `tests/generar_fixtures.py` a partir del `D` anterior. Replican la
  estructura de los originales, no su contenido real.

Los archivos reales del establecimiento no se versionan: contienen nombres y
resultados de estudiantes identificables. Para regenerar los sintéticos:

```bash
python tests/generar_fixtures.py
```
