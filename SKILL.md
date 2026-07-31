---
name: olympus-crm-analytics
description: Analytical queries on the Olympus CRM (IMB / IESL Institute). Use whenever the user asks about asesores, leads, oportunidades, matriculaciones, productos, países, cobranza, comisiones, costos, conversión, TC, time-to-first-sale, ramp-up, sensibilidad, ROI, people analytics, or references tables adm.Oportunidad, adm.HistorialEstado, adm.Personal, adm.Producto, adm.CobranzaPlan, adm.Persona, adm.PotencialCliente, mdm.Pais. Trigger on Olympus, IMB, IESL, asesores, leads, "dónde priorizar", "cuánto cuesta", "quién convierte más", course codes like imbpepkeyacc05261. PREFER bundled scripts (scripts/*.py) over running raw SQL — they are tested, parameterized, and pre-validate the gotchas. Use mcp__mssql__execute_sql only for ad-hoc questions not covered by an existing script.
compatibility: Requires LOCAL execution (Claude Code / local agent mode) — scripts connect via pyodbc + "ODBC Driver 18 for SQL Server" to a private SQL Server using credentials from a local .env. Does NOT work in a cloud sandbox (no network route to the DB, no ODBC driver).
---

# Olympus CRM Analytics

Skill for analyzing the Olympus CRM (IMB Institute / IESL Institute sub-brand) on SQL Server. Bundles **executable Python scripts** for the most common operations plus reference docs for ad-hoc queries.

**Ejecución local únicamente**: los scripts conectan a un SQL Server privado con credenciales del `.env` local y el driver ODBC 18. En un sandbox cloud (p. ej. el panel de Skills de Claude Desktop) no hay ruta a la BD ni driver — no intentes correrlos ahí.

## Decision tree: scripts vs MCP

**Use a bundled script when** the question matches one of the operations below. Scripts are faster, parameterized, and pre-validate the schema gotchas — Claude doesn't need to write or debug SQL.

**Fall back to `mcp__mssql__execute_sql`** when:
- The question is genuinely new (no script covers it).
- The user asks for a one-off exploration ("show me leads from Brazil that mention Power BI").
- A script exists but the user wants a variation that's not parameterized.

Whenever you fall back to MCP, **read `references/pitfalls.md` first** — there are 19 specific bugs that the scripts already handle but raw SQL doesn't.

## Available scripts

Run any of these from the skill root. All accept `-h/--help`. Default output is a pretty table; pass `--fmt csv -o file.csv` to save. **Detalle completo de flags, columnas y caveats por script: `references/scripts.md`** — léelo antes de interpretar columnas que no conozcas.

### Pipeline y asesores

| Script | Qué responde |
|---|---|
| `pipeline_kpis.py [--periodo 30]` | Snapshot global: asesores activos, llamadas, leads, matrículas, TC, tiempo a primer contacto. |
| `asesores_top.py [--top 20] [--bottom]` | Ranking de asesores. Mejores por Wilson LB; peores/menos eficientes con `--bottom` (Wilson UB asc). |
| `asesor_detail.py <id> [--periodo 90]` | Detalle individual de un asesor (KPIs, cobranza, Wilson LB). |
| `asesor_x_producto.py <id>` | Productos en los que un asesor vende mejor (Wilson LB desc). |
| `cohort_ramp.py --desde YYYY-MM-DD` | Ramp-up de asesores nuevos: leads y matrículas por mes desde su ingreso. |
| `time_to_first_sale.py [--desde YYYY-MM-DD]` | Días entre `FechaIngreso` y primera matriculación. |
| `asesores_por_area.py` | Compara asesores por área temática (Finanzas/RRHH/Otras): ¿el área es dura o los asesores producen mediocre? |
| `calls_by_hour.py [--periodo 30]` | Distribución de llamadas por hora con % contestadas y mejor franja. |
| `funnel_transitions.py [--asesor ID]` | Matriz de conversión por etapa — FLUJO entre etapas en una ventana. |

### Cursos y programas

| Script | Qué responde |
|---|---|
| `curso_report.py <codigo\|id>` | **Reporte completo de UN curso**, **SIEMPRE all-time** (nunca "últimos N días"): ficha + captación + funnel actual + esfuerzo + ingresos. NO calcula P&L. |
| `funnel_estado.py [codigo\|id]` | Estado ACTUAL del funnel: foto del stock por etapa vigente. Sin curso = global. |
| `product_search.py "patrón"` | Buscar cursos por nombre o código (devuelve `Codigo`, nunca el Id interno). |
| `cursos_en_venta.py [--desarrollador X] [--fmt xlsx]` | Cartera de cursos en estado "En venta" (catálogo `EstadoProductoTipoId=20`): funnel, inscritos, TC, TCProc, ingresos. Export Excel. |
| `programas_top_ventas.py [--desde/--hasta]` | Ranking de programas por ventas en una ventana, con TC de cohorte e ingresos. |
| `programas_performance.py [--periodo 60]` | Performance de ventana: TC + esfuerzo de llamadas + dinero + PerfScore 0-100. |
| `cohorte_tc_programas.py [--desde]` | TC de cohorte del mismo programa mes a mes, a madurez equivalente: ¿dónde mejoró/empeoró la conversión? |

### P&L y portafolio

| Script | Qué responde |
|---|---|
| `producto_pnl.py <codigo\|id> --cpl <USD> --docente <USD>` | P&L y sensibilidad de un producto. **CPL y docente OBLIGATORIOS — los da el usuario** (ver protocolo abajo). |
| `producto_compare.py <codigo> <codigo> …` | P&L de varios productos en una tabla (defaults homogéneos de `config.toml`). |
| `portafolio_encargado.py [--base creacion\|evento]` | Ingresos y estado del portafolio por encargado (`PersonalCreacion`). NO margen. **Mostrar siempre `%Total`** (ver protocolo abajo). |

### Marketing y campañas

| Script | Qué responde |
|---|---|
| `paises_priority.py [--tema "regex"]` | Ranking de países con Wilson LB para un set de productos. |
| `conversion_por_origen.py` | TC por origen del lead (Linkedin/Manual/Wordpress/FormularioWeb) con Wilson LB. Caveat de intención en `references/scripts.md`. |
| `linkedin_campanas.py [--buscar X]` | Campañas de LinkedIn (`FormName`) con naming pattern decodificado. |

### Calidad y docentes

| Script | Qué responde |
|---|---|
| `nps_encuesta_final.py [--nivel] [--timeline]` | NPS de la encuesta final por desarrollador / módulo / evolución temporal. |
| `pagos_docentes.py [--mes YYYY-MM] [--fmt fichas]` | Pagos a docentes: módulos que terminan de dictar en el mes, horas, fechas, Monto en blanco para completar. |

### Forecast

| Script | Qué responde |
|---|---|
| `forecast_programa.py --codigo <X> --cpl <PEN> --docente <PEN>` | Forecast GP + break-even de UN programa → CONTINUAR/RIESGO/CANCELAR (ver protocolo abajo). |

### Utilidades

| Script | Qué responde |
|---|---|
| `smoke_test.py` | Valida los módulos sin tocar la DB (pre-`.env`). |

### Mapeo de pregunta del usuario → script

| El usuario pregunta… | Corre… |
|---|---|
| "¿Cómo va el equipo este mes?" | `pipeline_kpis.py --periodo 30` |
| "¿Quiénes son los 10 mejores asesores?" | `asesores_top.py --top 10 --periodo 90` |
| "¿Quiénes son los peores?" / "¿Los menos eficientes?" / "¿Quién desperdicia más leads?" | `asesores_top.py --top 15 --bottom --periodo 90` (ordena por ineficiencia: alto volumen de leads con poca/ninguna venta, no solo 0 matrículas) |
| "Dame el detalle del asesor 81" | `asesor_detail.py 81` |
| "¿Cuánto cuesta procesar el producto imbpepkeyacc05261?" / "¿Rentabilidad del curso X?" | Preguntar CPL y pago docente al usuario → `producto_pnl.py imbpepkeyacc05261 --cpl <USD> --docente <USD>` |
| "¿Qué pasa si subimos el CPL a 0.30?" | `producto_pnl.py <codigo> --cpl 0.30` |
| "¿En qué países priorizar para cursos de mantenimiento?" | `paises_priority.py --tema "mantenimiento"` |
| "¿Cuánto tardan los asesores nuevos en cerrar su primera venta?" | `time_to_first_sale.py --desde 2026-01-01` |
| "¿Cuál es la mejor hora para llamar?" | `calls_by_hour.py --periodo 30` |
| "¿Cómo es el funnel del asesor 81?" | `funnel_transitions.py --asesor 81` |
| "Dame el reporte del curso X" / "¿Cómo va el curso X?" / "Todos los datos del curso imbpep…" | `curso_report.py <codigo>` (ficha + captación + funnel + esfuerzo + ingresos en una corrida; si quiere P&L/margen, además preguntar CPL y docente → `producto_pnl.py`) |
| "¿En qué estado está el funnel del curso 400?" / "¿Dónde están atascados los leads?" / "¿Cuántos leads vivos quedan?" | `funnel_estado.py 400` |
| "Dame un reporte de todos los cursos en venta" / "Cursos en venta del desarrollador X" / "Exporta a Excel los cursos en venta" | `cursos_en_venta.py` (`--desarrollador X`; `--fmt xlsx -o ruta.xlsx`). OJO: "en venta" = estado de catálogo, NO cualquier curso con ventas (para eso `programas_top_ventas.py`). |
| "¿En qué productos vende mejor el asesor 81?" / "¿Qué cursos son su fuerte?" | `asesor_x_producto.py 81 --periodo 90` |
| "¿Cómo va el ramp-up de los asesores que entraron este año?" | `cohort_ramp.py --desde 2026-01-01` |
| "¿Qué programas vendieron más en abril-mayo?" / "¿Cuánto se ha cobrado por curso?" | `programas_top_ventas.py --desde 2026-04-01 --hasta 2026-06-01 --top 25` |
| "¿En qué programas creció/cayó la conversión cohorte a cohorte?" | `cohorte_tc_programas.py --desde 2026-01-01 --mat-days 30` |
| "¿Qué programas tienen mejor performance considerando TC, llamadas y dinero?" | `programas_performance.py --periodo 60` |
| "Compara el P&L de estos cursos." / "¿Cuál da más margen?" | `producto_compare.py <codigo> <codigo> …` |
| "¿Cuánto ingresó/cobró cada persona de desarrollo / encargado?" / "¿Cómo está el portafolio de cada encargado?" | `portafolio_encargado.py` (ajusta `--comp-desde/--comp-hasta`; `--base evento` para caja por fecha de pago) |
| "¿Qué canal/origen convierte mejor?" / "¿De dónde vienen los leads aparte de LinkedIn?" | `conversion_por_origen.py` |
| "¿Cómo se llaman las campañas de LinkedIn?" / "¿Qué naming pattern siguen?" | `linkedin_campanas.py [--buscar X] [--por-formato]` |
| "¿Cuál es el NPS de la encuesta final?" / "¿Qué NPS tiene cada desarrollador / módulo?" | `nps_encuesta_final.py [--nivel detalle]` |
| "Haz el forecast del curso X" / "¿Llega este curso a break-even?" / "¿Conviene cancelarlo?" | `forecast_programa.py --codigo <X> --cpl <PEN> --docente <PEN>` (ver protocolo abajo — pedir al usuario los datos faltantes) |
| "Dame los pagos a docentes de este mes" / "¿Qué docentes terminan de dictar este mes?" / "Fichas de pago de junio" | `pagos_docentes.py [--mes YYYY-MM] [--desarrollador X] --fmt fichas` (fichas con Monto en blanco; sin `--fmt` da tabla) |

## SIEMPRE: estado actual del funnel en análisis de curso/programa

Cuando el usuario pregunte **cómo va un curso/programa** o pidas su performance/P&L
(p. ej. "¿cómo va el curso X?", `producto_pnl.py`, `programas_performance.py`,
`programas_top_ventas.py` para un programa puntual), **corre también
`funnel_estado.py <producto_id>` y muestra la foto del funnel** junto al resto del
análisis. El P&L y la TC de ventana dicen cuánto se vendió, pero no dónde está
parado el pipeline hoy; el estado actual del funnel revela cuántos leads siguen
vivos (Registrado/Calificado/Potencial/Promesa) vs. ya perdidos o sin calificar —
es lo que indica si el curso aún tiene recorrido o ya se agotó la demanda.

Preséntalo como una tabla corta de etapas con su conteo y %, más el resumen de
activas vs. matriculadas vs. perdidas/descartadas. Si no conoces el `producto_id`,
resuélvelo primero con `product_search.py`. Si el pedido es el **reporte general
de un curso** (no solo su P&L/performance), `curso_report.py` ya incluye esta
foto del funnel — no hace falta correr `funnel_estado.py` aparte.

## SIEMPRE: protocolo del forecast de programa (`forecast_programa.py`)

El forecast con Gaussian Processes funciona **para UN programa a la vez** — si el
usuario pide el forecast de varios cursos o de todo un portafolio, indícale que el
sistema multi-programa vive en el notebook de Colab
(`Work\Forecast\notebooks\forecast_colab.ipynb`, con Google Sheets) y ofrece correr
programas puntuales uno por uno con este script.

Protocolo obligatorio antes de correr:

1. **Resolver el programa**: si el usuario da un nombre (no un código/Id), corre
   `product_search.py "<nombre>"` primero y confirma cuál es.
2. **Reunir los 3 datos del usuario — NUNCA inventarlos ni estimarlos**:
   - **CPL en PEN** (costo por lead de ese programa) — siempre lo aporta el usuario.
   - **Costo docente en PEN** (por cohorte) — siempre lo aporta el usuario.
   - **Fecha de inicio** — el script la deriva solo de `Producto.FechaInicio` o del
     sufijo MMYY del `CodigoLanzamiento` (p.ej. `...05261` → 2026-05-01); si el
     script sale con código 3 listando `FALTAN_DATOS`, **pregunta al usuario**
     exactamente los campos listados y vuelve a correr con esos flags.
3. Si falta CPL o docente, pregunta ANTES de la primera corrida (ahorra un
   round-trip). El script sale con **exit code 3** y la lista de faltantes en
   stderr como red de seguridad.
4. Presenta el resultado completo: proyección de leads (media + optimista/pesimista),
   proyección de ventas al deadline (p05/media/p95), break-even y la **decisión**
   (CONTINUAR/RIESGO/CANCELAR) con su motivo. Si la decisión es CANCELAR, explica
   si es por margen ≤ 0 (estructural) o porque ni el escenario optimista llega.
5. La primera corrida en una máquina requiere `torch` + `gpytorch` instalados
   (ver Setup); la proyección asume flujo de leads "business as usual".

## SIEMPRE: CPL y pago docente del P&L los da el usuario (`producto_pnl.py`)

Antes de correr el P&L de un producto individual, **pregúntale SIEMPRE al usuario
el CPL (USD por lead) y el pago docente (USD) de ESE curso** — varían por curso y
correr con defaults da un P&L engañoso. NUNCA los inventes ni uses los de
`config.toml` sin confirmarlos.

1. Pregunta ambos valores ANTES de la primera corrida (ahorra un round-trip).
2. Corre `producto_pnl.py <codigo> --cpl <USD> --docente <USD>`.
3. Como red de seguridad, el script sale con **exit code 3** y la lista de
   faltantes en stderr si no se pasan ambos flags.

(`producto_compare.py` mantiene los defaults de `config.toml` para comparar
muchos cursos con supuestos homogéneos; si el usuario da CPL/docente, pásalos.)

## SIEMPRE: declarar la base temporal del reporte de portafolio por encargado

**`portafolio_encargado.py`** tiene el flag **`--base creacion|evento`** que
cambia realmente el anclaje de las columnas de plata:

- **`--base creacion` (DEFAULT, cohorte):** toda la plata pertenece a las
  oportunidades *creadas* en la ventana `[--comp-desde,--comp-hasta)`
  (`Oportunidad.FechaCreacion`), sin importar cuándo se pagó/matriculó. Cobrado =
  todos los pagos de esas oportunidades; comprometido = matrículas de esas
  oportunidades. **`TC` = conversión real de la cohorte** (numerador y denominador
  son el mismo set). Consistente con el portafolio y `LeadsVentana`, que ya se
  definen por `FechaCreacion`.
- **`--base evento` (ventana):** cobrado por `CobranzaPago.FechaPago` (desde
  `--desde`) y comprometido/`MatricVentana` por fecha de matrícula (estado 3) dentro
  de la ventana. Mide *caja que entró* / *ventas cerradas* en el período aunque el
  lead sea anterior. `TC` = proxy.

**Comportamiento requerido:** el default es **cohorte**. Al entregar el reporte,
**menciona siempre, al menos una vez, que también se puede calcular por ventana
(`--base evento`)** y qué mide cada base, para que el usuario elija con criterio. Si
el usuario ya pidió una base explícita, respétala; si no dijo nada, corre el default
(cohorte) y aclara la alternativa. Indica en el encabezado del reporte qué base se
usó (el script ya lo imprime en stderr).

## Setup (one-time)

```bash
# 1. Install dependencies (root install, no venv)
pip install -r requirements.txt

# 2. Copy .env.example to .env and fill in credentials
cp .env.example .env
# edit .env with DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME

# 3. Validate
python scripts/pipeline_kpis.py --periodo 7
```

If the validation prints a table of KPIs, setup is complete. If you get a connection error, the `.env` is wrong or the ODBC driver is missing (install Microsoft's "ODBC Driver 18 for SQL Server").

## Critical knowledge condensed

These are real bugs from past sessions. The scripts already handle them; only relevant if you fall back to raw MCP. **Fuente canónica: `references/pitfalls.md`** (19 bugs con root cause + fix) — esto es el resumen; ante duda o conflicto, manda pitfalls.md.

### Soft-delete is everywhere
Filter `Estado = 1` on every joined table: `Oportunidad`, `HistorialEstado`, `Producto`, `Personal`, `CobranzaPlan`, `CobranzaPago`, `Persona`. Personal also needs `ISNULL(Cesado, 0) = 0`.

### Country of the lead: NOT a direct join
`Oportunidad.IdPersona` is NULL in 95% of rows. Join through `PotencialCliente`:
```sql
Oportunidad → PotencialCliente.IdPersona → Persona.IdPais → mdm.Pais
```
Joining `op.IdPersona = per.Id` directly loses 95% of leads silently. (This bug made an analysis show 232 leads for Argentina when the real number was 13,271.)

### Origen del lead = canal; campaña sólo para LinkedIn
`Oportunidad.Origen` es el **canal de captación**, no la campaña. Valores reales:
`Linkedin` (~99%), `Manual`, `Wordpress`, `FormularioWeb`, `NULL`. El **nombre de
campaña** sólo existe para LinkedIn en **`adm.LinkedIn_Lead.FormName`** (el
`CampaignId` es numérico). No hay FK directa `Oportunidad`↔`LinkedIn_Lead`; se
relacionarían por email, fuera de alcance de los scripts. `adm.LinkedIn_Lead` **no
tiene `Estado`** (sin soft-delete); `TestLead=1` marca leads de prueba.
- **Naming pattern de FormName**: `[FOR-]<FORMATO><TEMA>[NIVEL][SEGMENTO]`,
  MAYÚSCULAS pegadas sin separador. `FORMATO ∈ {PAE, CEP, PEP, PAD}` cubre >94% de
  los leads; `FOR-` es la variante "formulario" del mismo código; cola larga ad-hoc
  (`WOMANLEAD`, `PUENTES DE PAPEL`, `HABISITE2026`…) rompe el patrón. `linkedin_campanas.py` lo parsea.
- **TC por origen NO es comparable a igualdad de intención**: `Manual` infla TC por
  sesgo de selección (el asesor lo crea cuando el lead ya está caliente);
  `FormularioWeb`/`Wordpress` son inbound de alta intención; `Linkedin` es lead-gen
  frío y masivo (TC ~0,3% pero aporta >50% de las matrículas absolutas). Para decidir
  presupuesto, cruzar con costo (CPL × leads) → **costo por matrícula**, no la TC sola.
  `conversion_por_origen.py` da la comparación con Wilson LB.

### Call counters are cumulative — use deltas
`CantidadLlamadasContestadas` and `CantidadLlamadasNoContestadas` are running totals per oportunidad. To count calls in a period, take the delta between consecutive rows. ~7K rows have decrements; clamp negatives with `MAX(0, current - LAG)`.

### Time to first contact — don't use `> 0`
First row of `HistorialEstado` already has calls > 0. Use the **second row by chronological order** (`ROW_NUMBER() = 2`).

### Matrícula attribution
Atribuir al `IdPersonal` de la fila con `IdEstado = 3` (asesor que cerró), no al primer asesor que tocó el lead. Dedupe con `COUNT(DISTINCT IdOportunidad)` porque ~120 leads tienen múltiples filas con estado 3.

### IdPersonal vs IdAsesor
`HistorialEstado.IdAsesor` es legacy. Usa `IdPersonal` siempre. Filtra `IdPersonal IS NOT NULL`.

### Encargado del curso = `Producto.PersonalCreacion` (con basura)
Para agrupar por "persona de desarrollo / encargado del producto" usa `Producto.PersonalCreacion`. **Está sucio**: ~60 productos lo tienen NULL (sin encargado) y hay `PersonalCreacion` huérfanos que no existen en `adm.Personal` (ids de prueba, p.ej. 165 y 218). Siempre **`INNER JOIN adm.Personal`** sobre ese campo — descarta NULL y huérfanos de una. Patrick Ramírez figura como encargado de ~78 productos (es válido, pero ojo: el campo es en parte "creador del registro", no siempre el desarrollador real). `portafolio_encargado.py` ya aplica este filtro.

### Docente fijo: solo a cohortes dictadas
El costo docente ($1440) es por cohorte. **No lo cargues a productos con 0 matrículas** (pilotos/preventa sin ventas) o inflas el costo con docentes fantasma — un dueño de 78 productos tendría ~425K PEN de docente irreal. `producto_pnl.py` aplica a un producto puntual (siempre dictado); en agregados multi-producto, condiciona el docente a `Matric > 0`.

### MCP CSV parsing — comma escape
El MCP devuelve CSV sin quoting. Si un nombre tiene coma, el parseo se rompe. Defensa: `REPLACE(field, ',', '~~')` en SQL, des-escapar en cliente. (Los scripts usan pyodbc directo, no tienen este problema.)

### MCP timeouts / "Rows affected: -1"
Cuando el MCP devuelve "Rows affected: -1": (1) quita TOP+ORDER BY del outer, (2) baja filtros al subquery interno, (3) divide en queries más simples. CTEs (`WITH`) a veces fallan via MCP — usa subqueries inline.

### Estados (lead status)
1=Registrado · 2=No calificado · 3=Matriculado (won) · 4=Calificado · 5=Potencial · 6=Promesa · 7=Perdido (lost).
Activos: 1, 4, 5, 6. Cerrados: 3, 7, 2.

### Tipos de jornada
31=Tiempo Completo, 32=Tiempo Parcial. En `Personal.IdTipoJornada`.

### Sales data start: 2026-01-01 (P15)
Los datos de ventas / llamadas / leads se registran sólo desde `2026-01-01`, pero `Personal.FechaIngreso` para el ~48% de asesores activos es anterior (algunos desde 2005). Para TTFS / cohort / ramp-up, los scripts usan `MAX(FechaIngreso, SALES_DATA_START)` por default ("sales mode"). Para tenure / rotación / HR pasar `--hr-mode` a `time_to_first_sale.py` y `cohort_ramp.py`. La fecha es configurable via `SALES_DATA_START_DATE` en `.env`.

### Cost model (defaults, override via flags or .env)
- Salario base: **565 PEN** (proporcional al peso del asesor en el producto)
- CPL: **$0.20 USD** por lead
- Docentes: **$1,440 USD** fijo por cohorte
- Comisión asesor: **10%** cobrado (solo a los que convierten)
- Comisión admin: **10%** cobrado
- USD→PEN: **3.78**

**NUNCA multipliques 565 × N asesores.** Usa atribución proporcional vía `lib/calc.py::fte_equivalents`. `producto_pnl.py` ya lo hace.

### Rankings: Wilson, no TC cruda
Para rankings de **mejores** conversores, ordena por Wilson lower bound 95%, no por TC. Muestra ambas columnas. `asesores_top.py` y `paises_priority.py` lo hacen. Para rankings de **peores / menos eficientes**, ordena por Wilson *upper* bound ascendente (`lib.calc.wilson_ub`): el LB empata a todos los de 0 matrículas en 0 sin importar el volumen, mientras el UB sube a quien más leads quemó con poca/ninguna venta (0/1376 tiene UB mucho menor que 0/30).

### P&L: SIEMPRE exacto vía script — nunca aproximar a mano
La rentabilidad/margen se calcula **solo por producto**. Para cualquier margen / rentabilidad / ganancia usa el valor exacto del script, **nunca** reconstruyas el P&L con cuentas manuales (ingreso×0.8 − CPL − docente…). Las aproximaciones se desvían y pierden el FTE, el breakeven y los matices. Guía:
- **Un producto** → `producto_pnl.py <id>`.
- **Varios productos / desglose curso a curso de un portafolio** → `producto_compare.py <id> <id> …` (una fila exacta por producto).
- **Override de supuestos** (CPL, salario, docente, comisiones, TC, USD/PEN): pásalos por flag; no recalcules el efecto a mano.

Para el **agregado de un portafolio por encargado** hay `portafolio_encargado.py`, pero ese reporte **solo da ingresos y estado de portafolio (no margen)**. Si necesitas la rentabilidad del portafolio, corre `producto_compare.py` con los `<id>` de sus productos y suma fila por fila. **Ojo: `producto_compare`/`producto_pnl` cargan el docente fijo a TODO producto, incluidos los de preventa sin dictar (matrículas=0) — eso sobreestima la pérdida de cohortes que aún no se dictan.** Si sumas a mano filas de `producto_compare` para un portafolio con preventas, descuenta el docente fantasma de esas filas.

## Reference files (read when needed)

- `references/scripts.md` — **Detalle de cada script**: flags completos, semántica de columnas, caveats. Lee antes de interpretar columnas desconocidas.
- `references/schema.md` — Tablas, columnas, FKs, soft-delete, enums. Lee antes de cualquier query nueva.
- `references/queries.md` — 18 templates SQL probados. Para ad-hoc via MCP.
- `references/calculations.md` — Wilson, FTE, sensibilidad, breakeven, BCG quadrants. Con worked example de imbpepkeyacc05261.
- `references/pitfalls.md` — 19 bugs reales con root cause + fix. Fuente canónica del "Critical knowledge".
- `references/postgres_migration.md` — Inventario T-SQL→PostgreSQL y pasos para la migración de proveedor.

## CLI conventions

- **Nombres canónicos de parámetros**: `--periodo N` (últimos N días), `--desde/--hasta` (ventana ISO `[desde, hasta)`, hasta exclusivo), `--top N` (filas, máx 500). Los nombres históricos siguen funcionando como alias (`--since` ≡ `--desde` en `time_to_first_sale.py` y `cohort_ramp.py`).
- **Identificador de cursos = CodigoLanzamiento**: `producto_pnl.py`, `producto_compare.py`, `funnel_estado.py` y `programas_performance.py --ids` aceptan el código directamente (o el Id interno como fallback) — ya NO hace falta resolver el Id con `product_search.py` antes.
- **Exit codes**: `0` ok · `1` sin resultados (id no encontrado, producto sin leads) · `2` error de entorno o parámetros (.env incompleto, fecha malformada) · `3` faltan datos que debe dar el usuario (protocolo del forecast).
- **Proveedor de BD**: se elige con `DB_DIALECT` en `.env` (hoy `mssql`; `postgres` stub para la migración). Driver, connection string y TLS/certificados viven en `lib/db_backends/` — no tocar scripts al cambiar de proveedor.

## Output conventions

- **Default output**: pretty table a stdout. Para guardar: `--fmt csv -o archivo.csv`.
- **Cursos SIEMPRE por su CodigoLanzamiento**: toda tabla a nivel curso muestra la columna `Codigo` y NUNCA el Id interno de `adm.Producto` (negocio trabaja con el código, el Id no le dice nada). Fallback `id:N` solo para productos sin código asignado.
- **Locale**: ES (números con coma como separador de miles cuando aplica).
- **Currency**: **TODO en USD por defecto** (decisión PM 2026-07-07; los montos de la BD ya están en USD). Cualquier reporte de dinero acepta `--moneda pen` para convertir con el `usd_pen` de `config.toml` (override con `--usd-pen`). Cuando muestres PEN, incluye siempre la conversión usada.
- **Parámetros de negocio**: viven en `config.toml` ([costos], [datos], [salida]) — fuente editable por negocio, versionada. Precedencia: flag CLI > .env > config.toml > default.
- **Caveats con cada número**: cuando reportes TC, incluye sample size. Cuando reportes promedio, di si excluiste outliers.
- **Recomendaciones**: agrupa en Tier 1/2/3/4 cuando el usuario pida "dónde invertir" o "a quién priorizar".

## Don't

- No multiplicar salario completo de cada asesor a un solo producto. Atribuye proporcional.
- No usar `Oportunidad.IdPersona` para país (NULL 95% de las veces).
- No mostrar TC cruda en rankings sin Wilson al lado.
- No usar `CantidadLlamadas > 0` para tiempo a primer contacto (usa rn=2).
- No omitir la moneda al mezclar USD y PEN.
- No olvidarse del soft-delete en JOINs.
- No inventar números cuando el MCP falla — reformula la query y reintenta.
- No aproximar el P&L / margen a mano — siempre el valor exacto de `producto_pnl.py` o `producto_compare.py` (rentabilidad = solo por producto).
- No mostrar el Id interno de un curso en tablas ni reportes — siempre su `CodigoLanzamiento`.
