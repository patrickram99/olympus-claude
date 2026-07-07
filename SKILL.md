---
name: olympus-crm-analytics
description: Analytical queries on the Olympus CRM (IMB / IESL Institute). Use whenever the user asks about asesores, leads, oportunidades, matriculaciones, productos, países, cobranza, comisiones, costos, conversión, TC, time-to-first-sale, ramp-up, sensibilidad, ROI, people analytics, or references tables adm.Oportunidad, adm.HistorialEstado, adm.Personal, adm.Producto, adm.CobranzaPlan, adm.Persona, adm.PotencialCliente, mdm.Pais. Trigger on Olympus, IMB, IESL, asesores, leads, "dónde priorizar", "cuánto cuesta", "quién convierte más", course codes like imbpepkeyacc05261. PREFER bundled scripts (scripts/*.py) over running raw SQL — they are tested, parameterized, and pre-validate the gotchas. Use mcp__mssql__execute_sql only for ad-hoc questions not covered by an existing script.
---

# Olympus CRM Analytics

Skill for analyzing the Olympus CRM (IMB Institute / IESL Institute sub-brand) on SQL Server. Bundles **executable Python scripts** for the most common operations plus reference docs for ad-hoc queries.

## Decision tree: scripts vs MCP

**Use a bundled script when** the question matches one of the operations below. Scripts are faster, parameterized, and pre-validate the schema gotchas — Claude doesn't need to write or debug SQL.

**Fall back to `mcp__mssql__execute_sql`** when:
- The question is genuinely new (no script covers it).
- The user asks for a one-off exploration ("show me leads from Brazil that mention Power BI").
- A script exists but the user wants a variation that's not parameterized.

Whenever you fall back to MCP, **read `references/pitfalls.md` first** — there are 19 specific bugs that the scripts already handle but raw SQL doesn't.

## Available scripts

Run any of these from the skill root. All accept `-h/--help`. Default output is a pretty table; pass `--fmt csv -o file.csv` to save.

| Script | What it answers |
|---|---|
| `scripts/pipeline_kpis.py [--periodo 30] [--jornada 31|32]` | Snapshot global: asesores activos, llamadas, leads, matrículas, TC, tiempo a primer contacto. |
| `scripts/asesores_top.py [--periodo 30] [--umbral 30] [--top 20] [--bottom]` | Ranking de asesores. **Mejores** (default): Wilson lower bound 95% desc. **Peores** (`--bottom`): **menos eficientes** por Wilson *upper* bound asc — sube a quien más leads quemó con poca/ninguna venta, no solo a los de 0 matrículas. Columnas extra: `LeadsxVenta` (leads por matrícula, `∞` si 0) y `WilsonUB%`. |
| `scripts/asesor_detail.py <id> [--periodo 90]` | Detalle individual de un asesor (KPIs, cobranza, Wilson LB). |
| `scripts/producto_pnl.py <id> [--moneda usd|pen] [--ingreso cobrado|comprometido] [--salario N] [--cpl N] [--comision-asesor N] [--comision-admin N] [--docente N] [--usd-pen N]` | P&L y análisis de sensibilidad de un producto. Soporta override de todos los parámetros vía flags. **Moneda por default USD** (`--moneda pen` para soles); los ratios (Margen %, Break-even TC) y el CPL máx no cambian con la moneda. |
| `scripts/paises_priority.py [--tema "mantenimiento|finanzas"] [--min-leads N]` | Ranking de países con Wilson LB para un set de productos. |
| `scripts/time_to_first_sale.py [--since YYYY-MM-DD] [--excluir-outliers 365]` | Días entre `FechaIngreso` y primera matriculación, CSV-ready. |
| `scripts/calls_by_hour.py [--periodo 30]` | Distribución de llamadas por hora 0-23 con % contestadas y mejor franja detectada. |
| `scripts/funnel_transitions.py [--asesor ID] [--periodo 90]` | Matriz de conversión por etapa (Reg→Cal+, Cal→Pot+, Pot→Prom+, Prom→Mat). FLUJO entre etapas en una ventana. |
| `scripts/funnel_estado.py [producto_id]` | Estado ACTUAL del funnel: foto del stock de oportunidades por etapa vigente (Registrado/Calificado/Potencial/Promesa/Matriculado/Perdido/No calificado), con activas vs. cerradas y TC actual. Sin id = global. |
| `scripts/product_search.py "patrón"` | Buscar productos por nombre o código de lanzamiento. Útil para encontrar el `producto_id` que luego le pasas a `producto_pnl.py`. |
| `scripts/cursos_en_venta.py [--desarrollador ID\|texto] [--excluir REGEX] [--usd-pen N] [--fmt table\|csv\|json\|xlsx] [-o ruta]` | **Cartera de cursos en estado "En venta"** (`Producto.EstadoProductoTipoId=20`) — los que HOY se comercializan, no cualquiera que haya vendido. Una fila por curso con: foto del funnel actual (Reg/Cal/Pot/Prom = stock vigente por etapa), `Ins` (inscritos = matriculados vigentes), `TC` (Ins/Leads %), `TCProc` (Ins sobre leads YA procesados = Ins/(Leads−Reg) %, excluye Registrado que aún no se llama), `Perdidos` (Perdido 7 + No calificado 2), `Comprometido`/`Cobrado`/`%Cob` en PEN (cohorte all-time del curso). `--desarrollador` filtra por encargado (`PersonalCreacion`): Id numérico o substring del nombre. `--excluir` es un regex case-insensitive sobre código+nombre para descartar paraguas de captación — **default `mundialer`** (excluye las campañas "Mundialero"); pasa `--excluir ""` para no excluir nada. `--fmt xlsx -o ruta.xlsx` escribe un Excel con encabezado formateado, panel congelado y autofiltro (columnas: Codigo, Curso, Leads, Reg, Cal, Pot, Prom, Ins, TC, TCProc, Perdidos, Comprometido, Cobrado, %Cob). Ordena por Ins desc. |
| `scripts/programas_top_ventas.py [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD] [--top 25] [--usd-pen N] [--max-usd-por-venta N]` | Ranking de programas por ventas en una ventana, con leads, TC de cohorte (conv/leads del período), ingreso comprometido y cobrado en PEN, %% cobrado y código del curso. Incluye análisis agregado de %% cobrado y un guard que marca/excluye montos comprometidos corruptos. |
| `scripts/asesor_x_producto.py <id> [--periodo 90] [--min-leads 5]` | Productos en los que un asesor vende mejor. Lista IdProducto, leads, matrículas, TC y Wilson LB ordenado por Wilson LB desc. |
| `scripts/cohort_ramp.py --since YYYY-MM-DD [--meses 6]` | Ramp-up de asesores nuevos: leads y matrículas por mes desde su `FechaIngreso`, columnas `M1_Leads, M1_Matric, …`. |
| `scripts/producto_compare.py <id> <id> [...] [--moneda usd|pen] [--ingreso ...] [--cpl N] [...]` | P&L de varios productos en una sola tabla (mismas overrides que `producto_pnl.py`). **Moneda por default USD** (`--moneda pen` para soles); Margen% y TC% no cambian. |
| `scripts/portafolio_encargado.py [--base creacion\|evento] [--desde 2026-01-01] [--comp-desde 2026-04-01] [--comp-hasta 2026-06-01] [--min-leads 20] [--historico]` | **Ingresos y estado actual del portafolio** por **persona de desarrollo / encargado del curso** (`Producto.PersonalCreacion`). **NO calcula rentabilidad/margen** — solo leads, matrículas, TC e ingresos (cobrado + comprometido en PEN). La rentabilidad se analiza por producto con `producto_pnl.py` / `producto_compare.py`. **Por default el portafolio = productos con `>=--min-leads` (20) leads CREADOS en la ventana** `[--comp-desde, --comp-hasta)` — el umbral corta cohortes viejas que solo captaron 1–7 leads de goteo (no es cartera real del período). Columnas `ProdConVenta` / `ProdSinVenta` / `Productos` (total) / `LeadsVentana` (leads creados en el período) / `MatricVentana` (matriculados de la ventana) / `TC` (con `--base creacion` = conversión real de cohorte; con `--base evento` = proxy) / `IngCobrado` / `%Cobrado` / `IngCompVentana`. Pasa `--historico` para el portafolio histórico completo, o `--min-leads 1` para incluir todo lo que captó algún lead. Excluye encargado NULL e ids huérfanos. |
| `scripts/cohorte_tc_programas.py [--desde YYYY-MM-DD] [--mat-days 30] [--min-leads 100] [--hoy YYYY-MM-DD]` | Compara la TC de cohorte de un mismo programa **mes a mes de captación, a madurez equivalente** (convertidos dentro de N días de la creación del lead). Agrupa productos por familia (código sin sufijo MMYYN), marca meses inmaduros (que aún no cumplen la ventana), y rankea familias por crecimiento de TC. Para "¿en qué programas mejoró/empeoró la conversión?". |
| `scripts/programas_performance.py [--periodo 60] [--min-ventas 5] [--min-leads 200] [--top 20] [--orden score\|cobrado\|eficiencia\|tc\|ventas] [--ids 1,2,3] [--desde/--hasta]` | Performance de programas en una ventana (NO cohorte): combina TC de ventana, **llamadas = esfuerzo de asesor** (delta de contadores), Llam/Venta, dinero cobrado/comprometido en PEN, Cobr/Llam (retorno al esfuerzo) y un PerfScore 0-100 (TC + dinero + eficiencia normalizados). `--ids` restringe a programas puntuales (combinar con `--desde 2026-01-01` para historia completa). Guard `--min-leads` corta denominadores minúsculos que inflan TC. |
| `scripts/asesores_por_area.py [--desde 2026-01-01] [--min-leads 80]` | Compara asesores por **área temática** (Finanzas/RRHH/Otras, inferida del nombre del producto). Vista 1 nivel área (TC, llamadas/lead, llamadas/venta → ¿el área es fácil o dura?); Vista 2 nivel asesor clasificado por área hogar (matrículas/asesor, TC, esfuerzo, Wilson → ¿producen mediocre?). Para testear hipótesis tipo "área consolidada = asesores sin motivación". |
| `scripts/conversion_por_origen.py [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD] [--incluir-eliminados]` | Compara la **TC global de cada origen del lead** (Linkedin/Manual/Wordpress/FormularioWeb/NULL) con leads, matrículas, TC%, **Wilson LB 95%** (muestras muy dispares) y % del total de matrículas. Convertido = alcanzó estado Matriculado. Incluye fila TOTAL. Para "¿qué canal convierte mejor?". OJO: las TC no son comparables a igualdad de intención (ver caveat abajo). |
| `scripts/linkedin_campanas.py [--buscar texto] [--por-formato] [--min-leads N] [--top N] [--sin-test]` | Lista las **campañas de LinkedIn** (`adm.LinkedIn_Lead.FormName`) con el **naming pattern decodificado** en columnas (EsForm `FOR-` / Formato `PAE\|CEP\|PEP\|PAD` / Resto = tema+nivel+segmento), leads y rango de fechas. `--buscar` filtra `FormName LIKE %texto%`; `--por-formato` agrega por prefijo de formato. Para "¿cómo se llaman las campañas?", "¿hay una campaña con X en el nombre?", "¿qué patrón siguen?". |
| `scripts/nps_encuesta_final.py [--nivel desarrollador\|modulo\|detalle] [--timeline dia\|semana\|mes] [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD] [--min-resp 5] [--ocultar-chicas]` | **NPS (Net Promoter Score) de la ENCUESTA FINAL** (`adm.EncuestaFinalRespuestas.RecomendacionEscala` 0-10) atribuido al **desarrollador del curso** (`Producto.PersonalCreacion`). Promotores 9-10 / Pasivos 7-8 / Detractores 0-6; NPS = %Prom − %Det. `--nivel desarrollador` (default) = 1 fila por dev; `--nivel modulo` = 1 fila por módulo; `--nivel detalle` = módulos agrupados bajo cada dev. **`--timeline [dia\|semana\|mes]`** (default semana) = evolución del NPS en el tiempo de TODAS las respuestas agregadas (ignora `--nivel`; combinar con `--desde/--hasta`). Marca con `*` muestras < `--min-resp`. Maneja el many-to-many módulo↔producto deduplicando módulo→desarrollador (atribución única a nivel dev). Fila TOTAL. |
| `scripts/forecast_programa.py --codigo <CodigoLanzamiento\|Id> --cpl <PEN> --docente <PEN> [--fecha-inicio YYYY-MM-DD] [--optimism 0.95] [--lookback N] [--min-valid-leads 100] [--usd-pen 3.78]` | **Forecast GP + break-even de UN programa** (Gaussian Processes con GPyTorch). Proyecta leads de la próxima semana (media, CI95, cuantiles optimista P80/P90/P95 y pesimista) y ventas acumuladas a la fecha de inicio (escenarios p05/media/p95), calcula N break-even y decide **CONTINUAR / RIESGO / CANCELAR** + leads/semana a solicitar. Ver protocolo obligatorio abajo. |
| `scripts/smoke_test.py` | Carga los módulos y valida el worked example sin tocar la DB — útil antes de configurar `.env`. |

### Mapeo de pregunta del usuario → script

| El usuario pregunta… | Corre… |
|---|---|
| "¿Cómo va el equipo este mes?" | `pipeline_kpis.py --periodo 30` |
| "¿Quiénes son los 10 mejores asesores?" | `asesores_top.py --top 10 --periodo 90` |
| "¿Quiénes son los peores?" / "¿Los menos eficientes?" / "¿Quién desperdicia más leads?" | `asesores_top.py --top 15 --bottom --periodo 90` (ordena por ineficiencia: alto volumen de leads con poca/ninguna venta, no solo 0 matrículas) |
| "Dame el detalle del asesor 81" | `asesor_detail.py 81` |
| "¿Cuánto cuesta procesar el producto imbpepkeyacc05261?" | `product_search.py imbpepkeyacc05261` → encontrar Id → `producto_pnl.py <Id>` |
| "¿Qué pasa si subimos el CPL a 0.30?" | `producto_pnl.py <Id> --cpl 0.30` |
| "¿En qué países priorizar para cursos de mantenimiento?" | `paises_priority.py --tema "mantenimiento"` |
| "¿Cuánto tardan los asesores nuevos en cerrar su primera venta?" | `time_to_first_sale.py --since 2026-01-01` |
| "¿Cuál es la mejor hora para llamar?" | `calls_by_hour.py --periodo 30` |
| "¿Cómo es el funnel del asesor 81?" | `funnel_transitions.py --asesor 81` |
| "¿En qué estado está el funnel del curso 400?" / "¿Dónde están atascados los leads de este programa?" / "¿Cuántos leads vivos quedan?" | `funnel_estado.py 400` |
| "Dame un reporte de todos los cursos en venta" / "¿Qué cursos están en venta y cómo va su funnel/inscritos/TC/ingresos?" / "Cursos en venta del desarrollador X" / "Exporta a Excel los cursos en venta" | `cursos_en_venta.py` (agrega `--desarrollador X` para filtrar por encargado; `--fmt xlsx -o ruta.xlsx` para Excel). OJO: "en venta" = estado de catálogo `EstadoProductoTipoId=20`, NO cualquier curso con ventas (para eso está `programas_top_ventas.py`). |
| "¿En qué productos vende mejor el asesor 81?" / "¿Qué cursos son su fuerte?" | `asesor_x_producto.py 81 --periodo 90` |
| "¿Cómo va el ramp-up de los asesores que entraron este año?" / "Compara el rendimiento mes a mes de la cohorte de enero." | `cohort_ramp.py --since 2026-01-01` |
| "¿Qué programas vendieron más en abril-mayo?" / "Top de cursos por ventas vs leads con TC e ingresos." / "¿Cuánto se ha cobrado por curso?" | `programas_top_ventas.py --desde 2026-04-01 --hasta 2026-06-01 --top 25` |
| "¿En qué programas creció/cayó la conversión cohorte a cohorte?" / "Compara la TC de las cohortes de los cursos." | `cohorte_tc_programas.py --desde 2026-01-01 --mat-days 30` |
| "¿Qué programas tienen mejor performance considerando TC, llamadas/esfuerzo y dinero?" / "¿Dónde rinde más el tiempo del asesor?" | `programas_performance.py --periodo 60` |
| "Compara el P&L de los productos 381, 382 y 388." / "¿Cuál de estos cursos da más margen?" | `producto_compare.py 381 382 388` |
| "¿Cuánto ingresó/cobró cada persona de desarrollo / encargado de los cursos?" / "¿Cómo está el portafolio de cada encargado (leads, matrículas, TC, cobrado)?" | `portafolio_encargado.py` (ajusta `--comp-desde/--comp-hasta`; `--base evento` para caja por fecha de pago) |
| "¿Qué canal/origen convierte mejor?" / "Compara la TC por origen del lead." / "¿De dónde vienen los leads aparte de LinkedIn?" | `conversion_por_origen.py` |
| "¿Cómo se llaman las campañas de LinkedIn?" / "¿Qué naming pattern siguen?" / "¿Hay una campaña con 'X' en el nombre?" | `linkedin_campanas.py [--buscar X] [--por-formato]` |
| "¿Cuál es el NPS de la encuesta final?" / "¿Qué NPS tiene cada desarrollador / cada módulo?" / "¿Qué módulos de cada desarrollador tienen mejor/peor recomendación?" | `nps_encuesta_final.py [--nivel detalle]` |
| "Haz el forecast del curso X" / "¿Cuántos leads necesita el programa X?" / "¿Llega este curso a break-even?" / "¿Conviene cancelar el programa X?" | `forecast_programa.py --codigo <X> --cpl <PEN> --docente <PEN>` (ver protocolo abajo — pedir al usuario los datos faltantes) |

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
resuélvelo primero con `product_search.py`.

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

These are real bugs from past sessions. The scripts already handle them; only relevant if you fall back to raw MCP.

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

- `references/schema.md` — Tablas, columnas, FKs, soft-delete, enums. Lee antes de cualquier query nueva.
- `references/queries.md` — 16 templates SQL probados. Para ad-hoc via MCP.
- `references/calculations.md` — Wilson, FTE, sensibilidad, breakeven, BCG quadrants. Con worked example de imbpepkeyacc05261.
- `references/pitfalls.md` — 19 bugs reales con root cause + fix.

## Output conventions

- **Default output**: pretty table a stdout. Para guardar: `--fmt csv -o archivo.csv`.
- **Locale**: ES (números con coma como separador de miles cuando aplica).
- **Currency**: los reportes de portafolio/ventas van en PEN por defecto; **los P&L (`producto_pnl.py` / `producto_compare.py`) van en USD por defecto** (`--moneda pen` para soles). USD donde la fuente lo está. Siempre incluir la conversión usada (USD/PEN).
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
