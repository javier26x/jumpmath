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
| `tests/` | 97 tests, incluida la reconstrucción completa del informe 4° A. |

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

### Tres reglas que no son obvias

Ambas se descubrieron contrastando contra el informe publicado y están fijadas
por tests; conviene no “simplificarlas”.

**1 · La alternativa correcta es la que va en negrita, no la más marcada.**
El informe destaca la clave en negrita, pero el PDF no usa una fuente bold:
simula la negrita rellenando y además trazando el glifo, y el único rastro es
que esos caracteres fijan un color de trazo RGB donde el resto deja el gris por
defecto. En 4° A de Escuela Santa Rosa, **7 de las 31 preguntas** tienen la
clave fuera de la alternativa más elegida; la P7 la marcó el 9,68 % del curso
mientras dos distractores empataban en 38,71 %. Resolver por el máximo publica
un 39 % donde va un 10 %. Ver `_es_negrita` en
`functions/jumpdia/parsers/dia_oficial.py`.

**2 · El % de una pregunta y su aporte al eje son números distintos.**
La P5 de 4° A se publica como **38 %** (respuestas completamente correctas),
pero pesa **50 %** en el promedio de Números y operaciones, porque la Agencia
puntúa con medio punto la respuesta parcialmente correcta (23 % del curso).
Usar el 38 % en el promedio deja el eje en 75,6 % en vez del 76,4 % oficial.
Ver `logro_mostrado` y `logro_puntaje` en `functions/jumpdia/reglas.py`.

**3 · El global del estudiante se calcula sobre aciertos, no sobre los
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

Los parsers no fijan posiciones: la tabla del PDF se localiza por coordenadas
de palabra y las planillas por la fila de encabezado que mejor casa con un
conjunto de sinónimos. Toleran cambios de orden, filas de título arriba y
variaciones de redacción.

| Archivo | Qué se lee |
|---|---|
| **Informe oficial DIA** (PDF) | Del encabezado: establecimiento, RBD, curso, docente, director, fecha y N° de estudiantes. De la «Tabla 1»: N° de pregunta, OA, eje, habilidad, indicador y la distribución de respuestas, con la clave destacada en negrita. |
| **Resultados por estudiante** (xlsx/PDF) | `Estudiante`, una columna por eje y `Nivel de logro`. Opcionales pero recomendadas: `Puntaje obtenido` y `Global`. |
| **Recomendaciones por indicador** (xlsx) | `N° de pregunta`, `Indicador`, `Sugerencias` y las columnas `Tomo 4.1` / `Tomo 4.2` del encabezado de dos filas. Opcional: `Análisis adicional`. |
| **Seguimiento JUMP** (xlsx) | Una hoja por evaluación, con la corrección ítem a ítem. La unidad sale del título de la hoja y el % se calcula. También se acepta el formato resumido de una fila por unidad. |
| **Plan Anual** (xlsx/PDF, opcional) | `Unidad`, `Mes`/`Fecha`. Si no calza, se ignora sin abortar la ingesta. |

Cuando algo no calza, el error dice qué columna falta, en qué archivo y qué
sinónimos se aceptan.

### Detalles del formato real que condicionan el parser

Se descubrieron abriendo los archivos de un establecimiento y cada uno está
cubierto por un test:

- **La «Tabla 1» del PDF no tiene rejilla.** Es texto en columnas con celdas
  que envuelven, así que `extract_tables` no sirve; las columnas se deducen
  proyectando las palabras sobre el eje horizontal y cortando por los cinco
  huecos más anchos.
- **Los Gráficos 1 y 2 son imágenes sin capa de texto**, de modo que del PDF
  no se pueden leer ni los niveles de logro ni el promedio por eje. Los
  niveles se agregan desde la nómina —donde vienen ya clasificados por la
  Agencia, uno por estudiante— y los promedios por eje se calculan desde las
  preguntas. Contar la clasificación oficial no es recalcularla con cortes de
  porcentaje, que es lo que la guía prohíbe.
- **El seguimiento trae una hoja por evaluación**, no una tabla de unidades.
  Hay unidades con varias evaluaciones (se informa el promedio) y hojas
  preparadas pero sin aplicar, que deben quedar *sin registro* y no como 0 %.
  Al pie de cada nómina hay una fila **«Total por pregunta»** con la misma
  forma que un estudiante: contarla mete la suma de la columna en el promedio.
- **La unidad de una hoja se resuelve por número y nombre.** El número solo no
  basta: «Unidad 1» es *Series* en el Tomo 4.1 y *Figuras* en el 4.2. La
  comparación es por similitud porque las planillas traen erratas
  («Undades métricas y tiempo» es un caso real).
- **El encabezado de las recomendaciones ocupa dos filas**: «Unidad JUMP Math»
  abarca dos columnas y sólo la fila de abajo dice cuál es cada tomo. El cruce
  con el informe se hace por N° de pregunta, no por el texto del indicador.

### Un PDF escaneado

Si el informe oficial viene escaneado, no hay texto que extraer y la ingesta
falla con ese diagnóstico. Para esos casos se declara
`google-cloud-documentai` y se activa con `JUMPDIA_DOCAI_PROCESSOR`; el OCR
todavía **no está conectado** (ver *Lo que falta*).

## Despliegue

Requiere un proyecto de Firebase con Blaze (las funciones de 2ª generación lo
exigen) y `firebase-tools`.

```bash
firebase use jumpmathv2             # ya está como alias por defecto en .firebaserc
firebase deploy --only firestore:rules,storage:rules
firebase deploy --only functions
firebase deploy --only hosting
```

Los dos hooks de `predeploy` de `firebase.json` dejan todo listo solo:

- `scripts/sync_plantilla.sh` copia la plantilla dentro de `functions/`, porque
  el despliegue sólo empaqueta ese directorio. `public/index.html` sigue siendo
  la única copia versionada.
- `scripts/preparar_functions.sh` crea `functions/venv` e instala las
  dependencias. El CLI importa el código para descubrir qué funciones hay y sin
  ese entorno aborta con *«Missing virtual environment at venv directory»*. Es
  sólo local —el runtime de producción lo construye Google— y se reinstala
  únicamente cuando cambia `requirements.txt`. Si la máquina no tiene el
  intérprete exacto del runtime declarado, avisa y usa el `python3` disponible.

### Lo que hay que habilitar una vez en la consola

Ninguna de las tres la puede hacer el CLI, y el despliegue falla sin las dos
primeras:

| Qué | Dónde | Si falta |
|---|---|---|
| Plan **Blaze** | Uso y facturación | `functions` no puede habilitar `cloudbuild` |
| **Cloud Storage** | Build → Storage → *Comenzar* | `storage` no encuentra el bucket |
| Acceso con **Google** | Authentication → Sign-in method | El deploy pasa, pero el docente no puede entrar |

El frontend ya apunta al proyecto **`jumpmathv2`** en
`public/firebase-config.js`. Esos valores son públicos por diseño —viajan al
navegador en cualquier app web de Firebase e identifican el proyecto, no
autorizan nada—, así que el archivo se versiona; lo que protege los datos son
las reglas de Firestore y Storage. Para apuntar a otro proyecto (uno de
pruebas, por ejemplo) está `public/firebase-config.example.js`.

**Sin `firebase-config.js` el informe sigue funcionando solo**, con los datos
de ejemplo y el Paso 1 como maqueta: es la condición de la guía §1 y conviene
no romperla.

El SDK se carga como módulo ES desde `gstatic.com`, no desde npm: no hay paso
de build en este proyecto, así que `import { initializeApp } from "firebase/app"`
—que necesita un bundler— no funcionaría. `public/app.js` importa la misma
librería por URL. Dos tests comprueban que la región y el proyecto del cliente
no se separen de los del backend, porque ese desajuste no se ve al desplegar:
falla recién al usarlo.

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

- **Los parsers se ejercitaron contra un solo establecimiento.** El pipeline
  procesa de extremo a extremo los cinco archivos de 4° A de Escuela Santa Rosa
  (RBD 5583) y los fixtures sintéticos reproducen esa estructura, pero un
  segundo colegio puede traer variantes de encabezado todavía no vistas.
  `scripts/ingesta_local.py` está pensado para esa vuelta: procesa un curso sin
  desplegar nada y muestra el diagnóstico completo.
- **El OCR de Document AI está declarado pero no conectado**: un informe
  oficial escaneado falla con un diagnóstico claro, no con un informe vacío.
- **`recs[].plus` se lee de la planilla**, como indica la guía §4, de una
  columna de análisis que es opcional. La planilla de Escuela Santa Rosa no la
  trae, así que ese bloque sale vacío en su informe. Varios de los textos del
  informe 4° A de referencia parecen redactados a partir de los datos del
  propio DIA (distractores, caída respecto del control JUMP); si esa
  generación debe automatizarse, es un módulo aparte.
- **La lógica de navegador no tiene tests automáticos.** `public/app.js` se
  verificó a mano en Chromium; los 97 tests cubren el pipeline de Python.
