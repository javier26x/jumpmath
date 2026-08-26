# Guía de integración — Prototipo Informe DIA 4° Básico (JUMP Math)

Archivo: `informe_dia_4b_bulnes_v2.html`

## 1. Qué es y qué NO es
Un **único archivo HTML autocontenido** (HTML + CSS + JS + logo en base64 + gráficos SVG).
No requiere build, framework, backend, ni librerías/CDN externos. Única dependencia externa
opcional: Google Fonts (se puede quitar; hay fallbacks del sistema).

El prototipo tiene ahora tres partes:
1. **Paso 1 · Carga de archivos** → *es una MAQUETA* (solo interfaz, sin procesamiento real).
2. **Informe** (5 secciones: Panorama, Por estudiante, Por indicador, Cobertura JUMP, Recomendaciones) → **la salida ya procesada**.
3. **Paso 6 · Descargar PDF** → exporta el informe completo usando el diálogo de impresión del navegador (sin librerías).

**Importante:** el prototipo es la **capa de salida**. La lectura de los archivos crudos y el
cálculo de resultados **no** están implementados: son un **módulo de backend** a construir
(ver §4). Hoy el informe mostrado corresponde a datos ya procesados del curso de ejemplo.

## 2. Cómo cargarlo
- Página independiente: servir el `.html` tal cual, o dentro de un `<iframe>`.
- Embebido: copiar `<style>`, el `<body>` (`<div class="wrap">…</div>`) y el `<script>` final.
  Aislar el CSS (contenedor propio o iframe) para evitar colisiones con estilos globales.
- Sin llamadas externas: eliminar del `<head>` las 3 líneas `<link ... fonts.googleapis ...>`.

## 3. El contrato de datos (objeto `D`)
Todo el contenido dinámico vive en **un solo objeto** al inicio del `<script>`: `const D = {…}`.
Para generar el informe de otro curso, el backend produce ese `D` y sirve el HTML. Estructura:

```
D.meta      = { colegio, rbd, curso, docente, director, n, fecha, prueba }
D.niveles   = { I, II, III }          // conteo de estudiantes por nivel OFICIAL DIA
D.ejes      = [5 strings]             // nombres de los ejes temáticos
D.ejeProm   = [5 numbers]             // % promedio de logro por eje (mismo orden que D.ejes)
D.ejeQC     = [15,3,4,6,3]            // N° de preguntas por eje (ponderación del global)
D.promGlobal= number                  // % de logro global del curso (ponderado por N° de preguntas)
D.students  = [ { n, nyo, pa, geo, med, dyp, g, lv } , ... ]   // lv = nivel DIA (1|2|3)
D.questions = [ { q, oa, eje, hab, ind, pct, sem, tipo, dist } , ... ]  // sem: 'V'|'A'|'R'
D.coverage  = [ { tomo, u, label, status, pct } , ... ]  // status: 'res' | 'none'
D.recs      = [ { q, oa, ind, pct, sem, units, estado, base, plus } , ... ]  // estado: 'remediar'|'esperado'
```

## 4. Especificación de ingesta — archivo → `D` (para el backend)
La pantalla de carga (Paso 1) espera estos archivos por curso. Así se mapea cada uno:

| Archivo que sube el usuario | Formato | Alimenta en `D` |
|---|---|---|
| **Informe oficial DIA** (ej. `RBD…_DIA_MATEMATICA_4_A_…pdf`) | PDF | `meta`, `niveles`, `ejes`, `ejeProm`, y por pregunta: `questions[].{oa,eje,hab,ind,pct,sem,tipo,dist}` |
| **Resultados por estudiante** (ej. `resultados_estudiantes_…pdf`) | PDF / xlsx | `students[]` (% por eje, nivel `lv` oficial), `n` |
| **Recomendaciones por indicador** (ej. `Recomendaciones por indicador 4° BP.xlsx`) | xlsx | `recs[].{ind,base,plus}` y el mapeo indicador → unidad JUMP (Tomo 4.1/4.2) |
| **Seguimiento de evaluaciones JUMP** (controles y pruebas) | xlsx | `coverage[].{label,status,pct}` y los `% ✓` de `recs[].units` |
| **Plan Anual del curso** (opcional) | xlsx / PDF | Referencia de secuencia esperada por fecha (nota de cobertura) |

**Reglas de negocio a respetar en el cálculo:**
- **Semáforo de % de logro:** verde ≥80% · amarillo 60–79% · rojo <60% (`sem` = V/A/R). Aplica a % por eje, pregunta y unidad.
- **Nivel del estudiante (`lv`) y `niveles`:** vienen del **informe oficial DIA** (metodología de la Agencia). **NO** calcular con cortes de %; un estudiante puede tener <60% global y ser Nivel II.
- **Global (`promGlobal`, `students[].g`):** % de logro sobre las 31 preguntas = promedio **ponderado por N° de preguntas de cada eje** (no promedio simple de las 5 columnas).
- **Cobertura JUMP:** `status:'res'` (con `pct`) solo para unidades con control/prueba **registrado**; `status:'none'` = sin registro (puede ser no trabajada, trabajada sin registrar, o prueba pendiente — no asumir "no trabajada").
- **Indicadores (`questions[].ind`):** usar la redacción textual del informe oficial DIA.
- **`recs[].estado`:** `'remediar'` si la unidad JUMP del indicador **ya se trabajó** (prioridad); `'esperado'` si aún no se aborda (secuenciar).
- **Nombres de unidades JUMP (`coverage[].label`):** usar el nombre original (Tomo 4.1: Series, Valor posicional/sumas y restas, Redondear, Multiplicar, Dividir, Unidades métricas y tiempo · Tomo 4.2: Figuras, Hallar el resto, Problemas, Fracciones, Decimales, Área y volumen, Ángulos y coordenadas, Diagramas).

## 5. Pantalla de carga (Paso 1) — es una maqueta
El panel `#uploadPanel` muestra 5 casilleros (4 obligatorios + Plan Anual opcional), permite
seleccionar archivos y marca "Cargado", habilitando el botón **Generar informe**. **No lee ni
procesa** los archivos: es solo la interfaz del flujo. El desarrollador debe conectar esos
`<input type="file">` a un endpoint que ejecute la ingesta de §4 y devuelva el objeto `D`.
La lista de fuentes está en la constante `SOURCES` del `<script>` (fácil de editar).

## 6. Descargar PDF (Paso 6)
La sección "Descargar PDF" (y el botón `#pdfBtn`) expande todas las secciones, despliega las
recomendaciones y abre el diálogo de impresión del navegador → elegir **"Guardar como PDF"**.
Usa reglas `@media print` (oculta navegación y panel de carga, saltos de página por sección);
**no** depende de ninguna librería. Si se prefiere generación server-side, puede reemplazarse
por un render headless (p. ej. Puppeteer/Playwright `page.pdf()`) del mismo HTML.

## 7. Datos del ejemplo
Curso 4° A · Colegio Manuel Bulnes Prieto (RBD 1886) · DIA Monitoreo Intermedio 2026.
Fuentes: informe oficial DIA, resultados por estudiante, "Recomendaciones por indicador 4° BP"
y el seguimiento de controles/pruebas JUMP. Se adjunta un PDF de ejemplo exportado del informe.
