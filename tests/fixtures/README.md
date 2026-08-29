# Fixtures

- **`D_4A_bulnes.json`** — el objeto `D` del informe 4° A ya publicado y
  revisado. Es la referencia dorada de los tests.
- **`dia_oficial_4A.pdf`, `estudiantes_4A.xlsx`, `recomendaciones_4B.xlsx`,
  `seguimiento_jump_4A.xlsx`** — archivos de entrada **sintéticos**, generados
  por `tests/generar_fixtures.py` a partir del `D` anterior.

Los sintéticos replican la **forma** de los originales, no sólo sus datos, y
eso es lo que les da valor: el PDF trae la Tabla 1 sin rejilla y con la clave
destacada en negrita, la planilla de recomendaciones tiene el encabezado de dos
filas con columnas por tomo, y el seguimiento trae una hoja por evaluación,
incluidas hojas preparadas sin aplicar y la fila «Total por pregunta» al pie de
cada nómina. Un fixture con tablas de bordes dibujados pasaría los tests sin
ejercitar nada de eso.

Los archivos reales del establecimiento no se versionan: contienen nombres y
resultados de estudiantes identificables. Para regenerar los sintéticos:

```bash
python tests/generar_fixtures.py
```
