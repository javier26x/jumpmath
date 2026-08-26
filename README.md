# Informe DIA · 4° Básico · JUMP Math

Backend de ingesta para el informe de resultados DIA: convierte los archivos
que sube el docente en el objeto `D` que consume el HTML del informe, y sirve
ese informe ya armado.

El prototipo de salida (el HTML autocontenido con las 5 secciones) ya existía;
lo que aquí se construye es lo que la
[guía del desarrollador](docs/GUIA_DESARROLLADOR_informe_dia.md) marcaba como
pendiente en su §4: **la lectura de los archivos crudos y el cálculo de
resultados**.

```
archivos del colegio  ──▶  Cloud Storage  ──▶  Cloud Function (Python)
                                                     │
                                     parsers ─▶ reglas ─▶ validación
                                                     │
                                                     ▼
                                              Firestore (D)  ──▶  HTML del informe
```

## Qué hay en el repositorio

| Ruta | Qué es |
|---|---|
| `functions/jumpdia/` | El pipeline de ingesta. No depende de Firebase ni de red. |
| `functions/main.py` | Las Cloud Functions que lo exponen. |
| `public/index.html` | El informe: es a la vez la app y la plantilla que rellena el backend. |
| `public/app.js` | Conecta el Paso 1 con Storage y con la función de ingesta. |
| `scripts/ingesta_local.py` | Corre la ingesta sin Firebase, para depurar planillas. |
| `tests/` | 80 tests, incluida la reconstrucción completa del informe 4° A. |

## Empezar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Para procesar un curso sin desplegar nada:

```bash
python scripts/ingesta_local.py \
  --dia "RBD1886_DIA_MATEMATICA_4_A.pdf" \
  --estudiantes resultados_estudiantes.pdf \
  --recomendaciones "Recomendaciones por indicador 4° BP.xlsx" \
  --seguimiento seguimiento_jump.xlsx \
  --salida informe_4A.html
```

Imprime el resumen del curso y los **avisos**: no son errores, son los
supuestos que la ingesta tuvo que tomar. Conviene leerlos antes de dar un
informe por bueno.

## Cómo se garantiza que el cálculo es correcto

`tests/fixtures/D_4A_bulnes.json` es el objeto `D` del informe 4° A ya
publicado y revisado. `tests/generar_fixtures.py` construye, a partir de él,
los cuatro archivos de entrada con la **estructura** de los originales, y el
test de extremo a extremo exige que el pipeline vuelva a producir ese mismo
`D`, campo por campo:

```
tests/test_pipeline.py::test_reconstruye_el_informe_publicado
```

Los archivos reales no están en el repositorio: traen nombres y resultados de
estudiantes identificables.

### Dos reglas que no son obvias

Ambas se descubrieron contrastando contra el informe publicado y están fijadas
por tests; conviene no “simplificarlas”.

**1 · El % de una pregunta y su aporte al eje son números distintos.**
La P5 de 4° A se publica como **38 %** (respuestas completamente correctas),
pero pesa **50 %** en el promedio de Números y operaciones, porque la Agencia
puntúa con medio punto la respuesta parcialmente correcta (23 % del curso).
Usar el 38 % en el promedio deja el eje en 75,6 % en vez del 76,4 % oficial.
Ver `logro_mostrado` y `logro_puntaje` en `functions/jumpdia/reglas.py`.

**2 · El global del estudiante se calcula sobre aciertos, no sobre los
porcentajes por eje ya redondeados.** Ponderando los enteros que muestra el
informe, 3 de los 26 estudiantes de 4° A se desvían en un punto:

| Estudiante | Desde % redondeados | Desde aciertos | Publicado |
|---|---|---|---|
| Guedez Suarez | 93,3 → 93 | 29/31 = 93,5 → **94** | 94 |
| Muñoz Fuenzalida | 69,5 → 70 | 21,5/31 = 69,4 → **69** | 69 |
| Roldán Morales | 51,4 → 51 | 16/31 = 51,6 → **52** | 52 |

Por eso el parser de estudiantes acepta una columna de puntaje o aciertos. Si
la planilla no la trae, el pipeline avisa de que el global va aproximado.

### Las reglas de la guía, y dónde viven

| Regla (guía §4) | Implementación |
|---|---|
| Semáforo V ≥80 · A 60–79 · R <60 | `reglas.semaforo` |
| El nivel del estudiante es el oficial del DIA, nunca un corte de % | `parsers/estudiantes.py`; test `test_niveles_vienen_del_pdf_no_de_cortes_de_porcentaje` |
| Global ponderado por N° de preguntas del eje | `reglas.promedio_global`, `reglas.global_estudiante` |
| `status:'none'` ≠ “no trabajada” | `parsers/seguimiento.py`; test `test_cobertura_sin_registro_no_es_cero` |
| Indicadores con la redacción textual del DIA | `parsers/dia_oficial.py` |
| `remediar` si la unidad JUMP ya se trabajó | `reglas.estado_recomendacion` |
| Nombres originales de las unidades JUMP | `catalogo.UNIDADES_JUMP` |

`functions/jumpdia/validacion.py` vuelve a comprobar todo esto sobre el `D`
final y aborta la ingesta si algo no cuadra, en vez de publicar un informe con
un número mal.

## Formato esperado de cada archivo

Los parsers no fijan posiciones de columna: buscan la fila de encabezado que
mejor casa con un conjunto de sinónimos, así que toleran que cambie el orden,
que haya filas de título arriba y que varíe la redacción del encabezado.

| Archivo | Columnas que necesita (o sinónimos) |
|---|---|
| **Informe oficial DIA** (PDF) | Tabla por pregunta con `N° Pregunta` e `Indicador`; se aprovechan además `OA`, `Eje`, `Habilidad`, `% Logro`, `Tipo` y la distribución (`A`–`E`, `RC`, `RPC`, `RI`, `N`). Fuera de la tabla: establecimiento, RBD, curso, docente, director, fecha y el conteo por nivel. |
| **Resultados por estudiante** (xlsx/PDF) | `Estudiante`, una columna por eje, `Nivel de aprendizaje`. Opcionales pero recomendadas: `Puntaje obtenido` y `Global`. |
| **Recomendaciones por indicador** (xlsx) | `Indicador`, `Unidad JUMP`, `Recomendación`. Opcional: `Análisis adicional`, `OA`. |
| **Seguimiento JUMP** (xlsx) | `Unidad JUMP`, `Promedio de logro`. Opcional: `Estado` (para distinguir *pendiente* de *sin resultado*). |
| **Plan Anual** (xlsx/PDF, opcional) | `Unidad`, `Mes`/`Fecha`. Si no calza, se ignora sin abortar la ingesta. |

Cuando algo no calza, el error dice qué columna falta, en qué archivo y qué
sinónimos se aceptan. Las unidades JUMP se reconocen escritas como
`Tomo 4.1 U2`, `4.1·U2`, `4.1 - Unidad 2` y variantes.

### Un PDF escaneado

Si el informe oficial viene escaneado, no hay texto que extraer y la ingesta
falla con ese diagnóstico. Para esos casos se declara
`google-cloud-documentai` y se activa con `JUMPDIA_DOCAI_PROCESSOR`; el OCR
todavía **no está conectado** (ver *Lo que falta*).

## Despliegue

Requiere un proyecto de Firebase con Blaze (las funciones de 2ª generación lo
exigen) y `firebase-tools`.

```bash
firebase use --add                  # elegir el proyecto; deja el alias en .firebaserc
firebase deploy --only firestore:rules,storage:rules
firebase deploy --only functions
firebase deploy --only hosting
```

`firebase.json` copia la plantilla dentro de `functions/` antes de desplegar
(`scripts/sync_plantilla.sh`), porque el despliegue sólo empaqueta ese
directorio. `public/index.html` es la única copia versionada.

Para el frontend, copie `public/firebase-config.example.js` a
`public/firebase-config.js` y complete los valores del proyecto. **Sin ese
archivo el informe sigue funcionando solo**, con los datos de ejemplo y el
Paso 1 como maqueta: es la condición de la guía §1 y conviene no romperla.

En local, con el emulador:

```bash
firebase emulators:start        # Hosting :5000 · Functions :5001 · UI :4000
```

### Qué usa de la plataforma

| Servicio | Para qué |
|---|---|
| **Hosting** | Sirve el informe y reescribe `/api/informe` a la función. |
| **Authentication** | Identifica al docente; su `uid` acota lo que puede leer y escribir. |
| **Cloud Storage** | Recibe los archivos en `cursos/{uid}/{cursoId}/{ranura}/`. |
| **Cloud Functions (2ª gen, Python 3.12)** | Ejecuta la ingesta y sirve el informe. Región `southamerica-west1`. |
| **Firestore** | Guarda el `D` de cada curso y su historial en `versiones/`. |
| **App Check** | Opcional; se activa con `appCheckSiteKey`. |
| **Emulator Suite** | Desarrollo local de los cinco servicios. |

### Sobre los datos personales

Los informes traen nombres y resultados de estudiantes. Las decisiones que hay
detrás de las reglas de seguridad:

- Storage y Firestore están particionados por `uid`: un docente sólo ve lo suyo.
- El `D` lo escriben **sólo** las Cloud Functions, que entran con credenciales
  de servicio y no pasan por las reglas. Desde el cliente `D` es de sólo
  lectura, así que nadie puede inventar un informe.
- Tipo y tamaño de archivo se validan en la regla de Storage, no sólo en la
  interfaz: el Paso 1 es una página web y se puede llamar al endpoint por fuera.
- `.gitignore` excluye `datos/` y `*.local.xlsx` para que un archivo real no
  llegue al repositorio por descuido.

## Lo que falta

- **Los parsers no se han ejercitado contra archivos reales.** Se escribieron
  contra la especificación de la guía §4 y se prueban con fixtures sintéticos
  que replican la estructura descrita, porque no se dispuso de un informe
  oficial DIA ni de las planillas del colegio. El PDF adjunto en
  `docs/informe_dia_4A_ejemplo.pdf` es la **salida** del prototipo, no una
  entrada. Al conectar el primer curso real es esperable tener que ampliar los
  sinónimos de encabezado y los patrones de `parsers/dia_oficial.py`;
  `scripts/ingesta_local.py` está pensado para esa vuelta.
- **El OCR de Document AI está declarado pero no conectado**: un informe
  oficial escaneado falla con un diagnóstico claro, no con un informe vacío.
- **`recs[].plus` se lee de la planilla**, como indica la guía §4. Varios de
  los textos del informe 4° A parecen redactados a partir de los datos del
  propio DIA (distractores, caída respecto del control JUMP); si esa
  generación debe automatizarse, es un módulo aparte.
