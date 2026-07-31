# Olympus CRM — Detalle de scripts

Documentación fina de cada script: flags completos, semántica de columnas y caveats.
La tabla resumida (qué script usar para qué pregunta) vive en `SKILL.md`; lee este
archivo cuando necesites el significado exacto de una columna o un flag antes de
correr o interpretar un script. Todos aceptan `-h/--help`.

## Table of contents

1. Pipeline y asesores — pipeline_kpis, asesores_top, asesor_detail, asesor_x_producto, cohort_ramp, time_to_first_sale, asesores_por_area, calls_by_hour, funnel_transitions
2. Cursos y programas — curso_report, funnel_estado, product_search, cursos_en_venta, programas_top_ventas, programas_performance, cohorte_tc_programas
3. P&L y portafolio — producto_pnl, producto_compare, portafolio_encargado
4. Marketing y campañas — paises_priority, conversion_por_origen, linkedin_campanas
5. Calidad y docentes — nps_encuesta_final, pagos_docentes
6. Forecast — forecast_programa
7. Utilidades — smoke_test

---

## 1. Pipeline y asesores

### `pipeline_kpis.py [--periodo 30] [--jornada 31|32]`
Snapshot global: asesores activos, llamadas, leads, matrículas, TC, tiempo a primer contacto.
`--jornada`: 31 = Tiempo Completo, 32 = Tiempo Parcial.

### `asesores_top.py [--periodo 30] [--umbral 30] [--top 20] [--bottom]`
Ranking de asesores.
- **Mejores** (default): Wilson lower bound 95% descendente.
- **Peores** (`--bottom`): **menos eficientes** por Wilson *upper* bound ascendente — sube
  a quien más leads quemó con poca/ninguna venta, no solo a los de 0 matrículas.
- Columnas extra: `LeadsxVenta` (leads por matrícula, `∞` si 0) y `WilsonUB%`.
- `--umbral`: leads mínimos para entrar al ranking (anti-outlier).

### `asesor_detail.py <id> [--periodo 90]`
Detalle individual de un asesor: KPIs, cobranza, Wilson LB.

### `asesor_x_producto.py <id> [--periodo 90] [--min-leads 5]`
Productos en los que un asesor vende mejor. Lista Codigo del curso, leads, matrículas,
TC y Wilson LB, ordenado por Wilson LB desc.

### `cohort_ramp.py --desde YYYY-MM-DD [--meses 6]`
Ramp-up de asesores nuevos: leads y matrículas por mes desde su `FechaIngreso`,
columnas `M1_Leads, M1_Matric, …`. Acepta `--hr-mode` (fecha de ingreso real, no
truncada a `SALES_DATA_START`).

### `time_to_first_sale.py [--desde YYYY-MM-DD] [--excluir-outliers 365]`
Días entre `FechaIngreso` y primera matriculación, CSV-ready. `--desde` tiene alias
retro-compatible `--since`. Acepta `--hr-mode`.

### `asesores_por_area.py [--desde 2026-01-01] [--min-leads 80]`
Compara asesores por **área temática** (Finanzas/RRHH/Otras, inferida del nombre del
producto). Vista 1 nivel área (TC, llamadas/lead, llamadas/venta → ¿el área es fácil o
dura?); Vista 2 nivel asesor clasificado por área hogar (matrículas/asesor, TC, esfuerzo,
Wilson → ¿producen mediocre?). Para testear hipótesis tipo "área consolidada = asesores
sin motivación".

### `calls_by_hour.py [--periodo 30]`
Distribución de llamadas por hora 0-23 con % contestadas y mejor franja detectada.

### `funnel_transitions.py [--asesor ID] [--periodo 90]`
Matriz de conversión por etapa (Reg→Cal+, Cal→Pot+, Pot→Prom+, Prom→Mat). Es **FLUJO
entre etapas en una ventana** — para la foto del stock actual usa `funnel_estado.py`.

## 2. Cursos y programas

### `curso_report.py <codigo|id> [--moneda usd|pen] [--usd-pen N]`
**Reporte completo de UN curso** en una sola corrida, **SIEMPRE all-time** (todas las
oportunidades asignadas al curso — nunca ventanas de "últimos N días"). Incluye:
- **Ficha**: nombre, desarrollador, estado de catálogo, precio base, fecha de inicio
  (inferida del sufijo MMYYN del código si la BD no la tiene).
- **Captación**: primer/último lead, leads totales.
- **Funnel actual**: stock por etapa + activos + TC/TCProc.
- **Esfuerzo**: asesores involucrados, llamadas contestadas/no contestadas acumuladas.
- **Ingresos**: comprometido/cobrado/%Cob, cohorte all-time, USD default.

Es el script para "dame el reporte del curso X". **NO calcula P&L** (eso es
`producto_pnl.py`, que pide CPL y docente al usuario).

### `funnel_estado.py [codigo|id]`
Estado ACTUAL del funnel: foto del stock de oportunidades por etapa vigente
(Registrado/Calificado/Potencial/Promesa/Matriculado/Perdido/No calificado), con
activas vs. cerradas y TC actual. Sin curso = global.

### `product_search.py "patrón"`
Buscar cursos por nombre o código de lanzamiento (devuelve el `Codigo`, nunca el Id
interno). Útil cuando el usuario da un nombre aproximado.

### `cursos_en_venta.py [--desarrollador ID|texto] [--excluir REGEX] [--usd-pen N] [--fmt table|csv|json|xlsx] [-o ruta]`
**Cartera de cursos en estado "En venta"** (`Producto.EstadoProductoTipoId=20`) — los
que HOY se comercializan, no cualquiera que haya vendido. Una fila por curso:
- Funnel actual: `Reg/Cal/Pot/Prom` = stock vigente por etapa.
- `Ins` = inscritos (matriculados vigentes) · `TC` = Ins/Leads % · `TCProc` = Ins sobre
  leads YA procesados = Ins/(Leads−Reg) %, excluye Registrado que aún no se llama.
- `Perdidos` = Perdido (7) + No calificado (2).
- `Comprometido`/`Cobrado`/`%Cob` en USD por defecto (`--moneda pen` convierte;
  cohorte all-time del curso).
- `--desarrollador`: filtra por encargado (`PersonalCreacion`), Id numérico o substring
  del nombre.
- `--excluir`: regex case-insensitive sobre código+nombre para descartar paraguas de
  captación — **default `mundialer`** (excluye las campañas "Mundialero"); pasa
  `--excluir ""` para no excluir nada.
- `--fmt xlsx -o ruta.xlsx`: Excel con encabezado formateado, panel congelado y
  autofiltro (columnas: Codigo, Curso, Leads, Reg, Cal, Pot, Prom, Ins, TC, TCProc,
  Perdidos, Comprometido, Cobrado, %Cob).
- Ordena por Ins desc.

### `programas_top_ventas.py [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD] [--top 25] [--usd-pen N] [--max-usd-por-venta N]`
Ranking de programas por ventas en una ventana, con leads, TC de cohorte (conv/leads del
período), ingreso comprometido y cobrado (USD por defecto; `--moneda pen` convierte),
% cobrado y código del curso. Incluye análisis agregado de % cobrado y un guard que
marca/excluye montos comprometidos corruptos (`--max-usd-por-venta`).

### `programas_performance.py [--periodo 60] [--min-ventas 5] [--min-leads 200] [--top 20] [--orden score|cobrado|eficiencia|tc|ventas] [--ids 1,2,3] [--desde/--hasta]`
Performance de programas en una ventana (NO cohorte): combina TC de ventana,
**llamadas = esfuerzo de asesor** (delta de contadores), Llam/Venta, dinero
cobrado/comprometido en PEN, Cobr/Llam (retorno al esfuerzo) y un PerfScore 0-100
(TC + dinero + eficiencia normalizados). `--ids` restringe a programas puntuales
(combinar con `--desde 2026-01-01` para historia completa). Guard `--min-leads` corta
denominadores minúsculos que inflan TC.

### `cohorte_tc_programas.py [--desde YYYY-MM-DD] [--mat-days 30] [--min-leads 100] [--hoy YYYY-MM-DD]`
Compara la TC de cohorte de un mismo programa **mes a mes de captación, a madurez
equivalente** (convertidos dentro de N días de la creación del lead). Agrupa productos
por familia (código sin sufijo MMYYN), marca meses inmaduros (que aún no cumplen la
ventana), y rankea familias por crecimiento de TC. Para "¿en qué programas
mejoró/empeoró la conversión?".

## 3. P&L y portafolio

### `producto_pnl.py <codigo|id> --cpl <USD> --docente <USD> [--moneda usd|pen] [--ingreso cobrado|comprometido] [--salario N] [--comision-asesor N] [--comision-admin N] [--usd-pen N]`
P&L y análisis de sensibilidad de un producto.
- **`--cpl` y `--docente` son OBLIGATORIOS y los da el usuario — pregúntaselos SIEMPRE
  antes de correr** (exit 3 si faltan). Ver protocolo en `SKILL.md`.
- **Moneda por default USD** (`--moneda pen` para soles); los ratios (Margen %,
  Break-even TC) y el CPL máx (ya en USD) no cambian con la moneda.
- `--ingreso cobrado` (default) usa lo pagado real; `comprometido` asume 100% de los
  planes de cobranza pagados.

### `producto_compare.py <codigo|id> <codigo|id> [...] [--moneda usd|pen] [--ingreso ...] [--cpl N] [...]`
P&L de varios productos en una sola tabla (mismas overrides que `producto_pnl.py`).
Mantiene los defaults de `config.toml` para comparar muchos cursos con supuestos
homogéneos; si el usuario da CPL/docente, pásalos. **Moneda por default USD**
(`--moneda pen` para soles); Margen% y TC% no cambian.
**Caveat**: carga el docente fijo a TODO producto, incluidos los de preventa sin dictar
(matrículas=0) — sobreestima la pérdida de cohortes aún no dictadas.

### `portafolio_encargado.py [--base creacion|evento] [--desde 2026-01-01] [--comp-desde 2026-04-01] [--comp-hasta 2026-06-01] [--min-leads 20] [--historico]`
**Ingresos y estado actual del portafolio** por **persona de desarrollo / encargado del
curso** (`Producto.PersonalCreacion`). **NO calcula rentabilidad/margen** — solo leads,
matrículas, TC e ingresos (cobrado + comprometido, USD por defecto; `--moneda pen`
convierte). La rentabilidad se analiza por producto con `producto_pnl.py` /
`producto_compare.py`.
- **Portafolio default** = productos con `>= --min-leads` (20) leads CREADOS en la
  ventana `[--comp-desde, --comp-hasta)` — el umbral corta cohortes viejas que solo
  captaron 1–7 leads de goteo (no es cartera real del período).
- Columnas: `ProdConVenta` / `ProdSinVenta` / `Productos` (total) / `LeadsVentana`
  (leads creados en el período) / `MatricVentana` (matriculados de la ventana) / `TC`
  (con `--base creacion` = conversión real de cohorte; con `--base evento` = proxy) /
  `IngCobrado` / `%Total` / `IngCompVentana`.
- **`%Total`** = participación del cobrado del encargado sobre el cobrado total del
  reporte, suma 100 — NO confundir con `%Cob` de `cursos_en_venta.py`, que es
  cobrado/comprometido. **Inclúyela siempre al presentar el reporte** — el usuario la
  usa para ver el peso de cada portafolio.
- `--historico` = portafolio histórico completo; `--min-leads 1` = todo lo que captó
  algún lead.
- Excluye encargado NULL e ids huérfanos.
- El flag `--base creacion|evento` cambia el anclaje temporal de la plata — ver la
  sección "SIEMPRE: declarar la base temporal" en `SKILL.md`.

## 4. Marketing y campañas

### `paises_priority.py [--tema "mantenimiento|finanzas"] [--min-leads N]`
Ranking de países con Wilson LB para un set de productos (filtrados por regex de tema).

### `conversion_por_origen.py [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD] [--incluir-eliminados]`
Compara la **TC global de cada origen del lead** (Linkedin/Manual/Wordpress/
FormularioWeb/NULL) con leads, matrículas, TC%, **Wilson LB 95%** (muestras muy
dispares) y % del total de matrículas. Convertido = alcanzó estado Matriculado. Incluye
fila TOTAL. Para "¿qué canal convierte mejor?".
**OJO**: las TC por origen NO son comparables a igualdad de intención (ver "Critical
knowledge" en `SKILL.md`).

### `linkedin_campanas.py [--buscar texto] [--por-formato] [--min-leads N] [--top N] [--sin-test]`
Lista las **campañas de LinkedIn** (`adm.LinkedIn_Lead.FormName`) con el **naming
pattern decodificado** en columnas (EsForm `FOR-` / Formato `PAE|CEP|PEP|PAD` / Resto =
tema+nivel+segmento), leads y rango de fechas. `--buscar` filtra `FormName LIKE %texto%`;
`--por-formato` agrega por prefijo de formato. Para "¿cómo se llaman las campañas?",
"¿hay una campaña con X en el nombre?", "¿qué patrón siguen?".

## 5. Calidad y docentes

### `nps_encuesta_final.py [--nivel desarrollador|modulo|detalle] [--timeline dia|semana|mes] [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD] [--min-resp 5] [--ocultar-chicas]`
**NPS (Net Promoter Score) de la ENCUESTA FINAL**
(`adm.EncuestaFinalRespuestas.RecomendacionEscala` 0-10) atribuido al **desarrollador
del curso** (`Producto.PersonalCreacion`).
- Promotores 9-10 / Pasivos 7-8 / Detractores 0-6; NPS = %Prom − %Det.
- `--nivel desarrollador` (default) = 1 fila por dev; `modulo` = 1 fila por módulo;
  `detalle` = módulos agrupados bajo cada dev.
- `--timeline [dia|semana|mes]` (default semana) = evolución del NPS en el tiempo de
  TODAS las respuestas agregadas (ignora `--nivel`; combinar con `--desde/--hasta`).
- Marca con `*` muestras < `--min-resp`. Fila TOTAL.
- Maneja el many-to-many módulo↔producto deduplicando módulo→desarrollador
  (atribución única a nivel dev).

### `pagos_docentes.py [--mes YYYY-MM] [--desarrollador ID|texto] [--async-horas 2] [--fmt table|csv|json|fichas] [-o ruta]`
**Pagos a docentes del mes**: módulos cuya **última sesión de clase**
(`adm.SesionHorario`, excluye la sesión de presentación) cae en `--mes` (default: mes
actual).
- Columnas: **docente nombre completo** (`Modulo.IdDocente → Docente → Persona`),
  **cursos padre** (`EstructuraCurricularModulo → EstructuraCurricular →
  Producto.CodigoLanzamiento`), **Horas** = en vivo reales + 2h asincrónicas
  (`--async-horas`), fechas de dictado (primera y última sesión) y **columna Monto
  (USD) VACÍA** que completa el usuario.
- `--desarrollador` filtra por encargado del curso padre (`Producto.PersonalCreacion`,
  Id o substring del nombre) y muestra solo los cursos de ese dev.
- `--fmt fichas` imprime el formato de ficha por docente (`NOMBRES Y APELLIDOS DEL
  DOCENTE: … / - Código de curso: … / - Monto (USD):`) que usa administración.
- Horas con `*` = sesiones registradas con duración cero en Olympus (estimadas a
  2h/sesión — corregir el registro).

## 6. Forecast

### `forecast_programa.py --codigo <CodigoLanzamiento|Id> --cpl <PEN> --docente <PEN> [--fecha-inicio YYYY-MM-DD] [--optimism 0.95] [--lookback N] [--min-valid-leads 100] [--usd-pen 3.78]`
**Forecast GP + break-even de UN programa** (Gaussian Processes con GPyTorch). Proyecta
leads de la próxima semana (media, CI95, cuantiles optimista P80/P90/P95 y pesimista) y
ventas acumuladas a la fecha de inicio (escenarios p05/media/p95), calcula N break-even
y decide **CONTINUAR / RIESGO / CANCELAR** + leads/semana a solicitar.
**Protocolo obligatorio en `SKILL.md`** (CPL y docente en PEN los da el usuario; fecha
de inicio derivable del sufijo MMYY del código). Requiere `torch` + `gpytorch`
(`requirements-forecast.txt`). Multi-programa vive en el notebook de Colab, no aquí.

## 7. Utilidades

### `smoke_test.py`
Carga los módulos y valida el worked example sin tocar la DB — útil antes de configurar
`.env`.
