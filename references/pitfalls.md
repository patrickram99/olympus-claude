# Olympus CRM — Pitfalls (real bugs from past sessions)

Each entry: the bug, the symptom, the root cause, the fix. Read this BEFORE writing queries for the first time.

## P1. `Oportunidad.IdPersona` is NULL 95% of the time

**Symptom**: A country breakdown reports tiny numbers (e.g., Argentina = 232 leads) when the user knows it's much larger. Most countries appear undercount or absent.

**Root cause**: Joining `adm.Persona per ON per.Id = op.IdPersona` excludes 95% of oportunidades because that FK is almost always NULL.

**Fix**: travel through `PotencialCliente`:
```sql
INNER JOIN adm.PotencialCliente pc ON pc.Id = op.IdPotencialCliente
INNER JOIN adm.Persona per         ON per.Id = pc.IdPersona
INNER JOIN mdm.Pais pa             ON pa.Id  = per.IdPais
```

After fix, Argentina total leads jumps from 232 to 13,271. Always validate large-country totals against the user's mental model.

---

## P2. `CantidadLlamadas > 0` returns ~0 minutes for time-to-first-contact

**Symptom**: "Tiempo a primer contacto" reports 0 minutos for almost every lead.

**Root cause**: The first `HistorialEstado` row for an oportunidad is created at the same moment as the oportunidad itself (often by the same system batch), and frequently already contains `CantidadLlamadasContestadas = 1` or `CantidadLlamadasNoContestadas = 1` from the call that generated the lead. So "first row where calls > 0" = the creation row = 0 minutes after creation.

**Fix**: use the *second* row by chronological order:
```sql
ROW_NUMBER() OVER (PARTITION BY IdOportunidad ORDER BY FechaCreacion, Id) = 2
```

That row represents the first time the asesor actually touched the lead (changed state, added notes, made another call).

---

## P3. Call counters can decrement

**Symptom**: Total calls per asesor inexplicably low; deltas show negative values.

**Root cause**: ~7,683 rows in `HistorialEstado` have lower `CantidadLlamadasContestadas` or `CantidadLlamadasNoContestadas` than the previous row for the same oportunidad. Causes: manual data corrections, asesor reassignments that reset counters, system migrations.

**Fix**: clamp deltas to non-negative:
```sql
CASE WHEN delta > 0 THEN delta ELSE 0 END
```

Never use raw `current - LAG` because it can produce negative call counts and bogus daily totals.

---

## P4. MCP doesn't return CSV with proper quoting

**Symptom**: A row of the response has more "columns" than headers; parsing breaks.

**Root cause**: The MSSQL MCP serializes rows as plain `value,value,value` without quoting. If a `Nombres` field contains a comma (e.g., "Smith, Jr."), the row splits into too many fields and downstream parsing breaks.

**Fix**: in SQL, escape commas in text columns before they go to the wire:
```sql
SELECT REPLACE(p.Nombres, ',', '~~') AS Nombre, ...
```

In client code, un-escape: `nombre.replace(/~~/g, ',')`.

---

## P5. "Rows affected: -1" — MCP timeout / oversized query

**Symptom**: A complex query returns "Rows affected: -1" with no data.

**Root cause**: The MCP wrapper has timeouts and may abort large query plans. Common triggers: outer `TOP N` + outer `ORDER BY` + 3+ joins + window function on 200K+ rows.

**Workarounds** (try in order):
1. Drop the outer `TOP` and `ORDER BY`; let the client filter/sort.
2. Push WHERE filters into the innermost subquery rather than the outer.
3. Replace correlated subqueries with one extra GROUP BY + JOIN.
4. Split the query: one query per chunk (per country, per asesor batch, etc.).
5. As last resort, materialize an intermediate set with a temp table — but the MCP doesn't allow `CREATE TABLE`, so this means several round trips.

Don't fabricate data when this hits. Re-engineer the query.

---

## P6. CTEs (`WITH`) sometimes fail silently via the MCP

**Symptom**: Query with a `WITH foo AS (...)` returns "Rows affected: -1" without an error message.

**Root cause**: Some versions of the MSSQL MCP don't handle CTEs reliably.

**Fix**: use inline subqueries (`SELECT ... FROM (SELECT ...) q ...`) instead of CTEs. Functionally identical, just verbose.

---

## P7. `Personal.FechaIngreso` has pre-CRM values

**Symptom**: Time-to-first-sale averages are dominated by one or two values like 7,561 or 8,981 days.

**Root cause**: A few asesores were migrated from a previous system and their `FechaIngreso` shows their original employment date (2001, 2005), not when they joined Olympus.

**Fix**: filter `DATEDIFF(day, FechaIngreso, primeraVenta) BETWEEN 0 AND 365`. Anything > 365 is almost certainly a data-quality issue. Optionally report both raw and filtered numbers and explain the exclusion.

---

## P8. Matrícula attribution: 120 oportunidades have multiple `IdEstado = 3` rows

**Symptom**: Counting matriculaciones returns slightly higher numbers than expected; some asesores have the same matrícula counted twice.

**Root cause**: Re-matriculations or state corrections create multiple rows with `IdEstado = 3` for the same `IdOportunidad`.

**Fix**: dedupe with `COUNT(DISTINCT IdOportunidad)` instead of `COUNT(*)` when counting matriculaciones. For attribution, take the *first* `IdEstado = 3` row per oportunidad:
```sql
ROW_NUMBER() OVER (PARTITION BY IdOportunidad ORDER BY FechaCreacion, Id) = 1
```
(where the subquery already filters to `IdEstado = 3`).

---

## P9. `HistorialEstado.IdAsesor` is a legacy column, not the asesor

**Symptom**: Joining `Personal` on `IdAsesor` returns far fewer rows than expected.

**Root cause**: `IdAsesor` was the original column, partially populated and partially replaced by `IdPersonal`. They differ for ~200K rows where both are present.

**Fix**: always use `IdPersonal`. Filter `IdPersonal IS NOT NULL`. Ignore `IdAsesor` entirely unless doing forensic history work.

---

## P10. Forgetting soft-delete on joined tables

**Symptom**: Totals over-count by 5-15% versus dashboard / source-of-truth comparisons.

**Root cause**: Filtering `op.Estado = 1` on the main table but not on `Producto`, `CobranzaPlan`, `Persona`, etc. Deleted dim rows still appear in joins.

**Fix**: add `AND <alias>.Estado = 1` to *every* join predicate, not just to the outer WHERE:
```sql
INNER JOIN adm.Producto pr ON pr.Id = op.IdProducto AND pr.Estado = 1
INNER JOIN adm.Persona per ON per.Id = pc.IdPersona AND per.Estado = 1
```

Yes, even for catalogs (`mdm.Pais`) — habit > minor query overhead.

---

## P11. Attributing the full salary of every asesor to one product

**Symptom**: A product appears wildly unprofitable (e.g., 67,138 PEN cost / 4,227 PEN revenue) when it shouldn't be.

**Root cause**: Multiplying `salarioBasePEN × NumAsesoresQueTocaron` overcounts because each asesor works dozens of products.

**Fix**: weight each asesor's salary by `leadsAsesorEnProducto / leadsAsesorTotal`. Sum the weights → FTE equivalents. See `calculations.md §2` and the worked example in §6.

After applying the fix on `imbpepkeyacc05261`: 116 asesores collapsed to **3.29 FTE**, salary cost dropped from 65,540 PEN to 1,861 PEN, and the product flipped from -52,000 PEN to +2,669 PEN.

---

## P12. Mixing USD and PEN without stating the conversion

**Symptom**: User questions "are these numbers in soles or dolares?" — trust eroded.

**Root cause**: `CostoBase`, `CobranzaPlan.Total`, `CobranzaPago.Monto` are in USD. The user thinks in PEN.

**Fix**: pick one currency, convert everything to it, and always state the rate used. Default conversion rate is 3.78 (USD→PEN). Make it configurable.

---

## P13. Showing TC alone without the muestra

**Symptom**: User asks "but why is asesor X ranked above Y? Y has way more sales."

**Root cause**: Showing crude TC ranking without sample size lets small-sample asesores top the chart with 1/3 (33%) beating someone with 50/1000 (5%).

**Fix**: always show `leads`, `matriculados`, `TC`, and `Wilson LB 95%` together. Rank by Wilson. Add a "muestra insuficiente" badge when `leads < umbral` (default 30).

---

## P15. `Personal.FechaIngreso` es pre-CRM para ~48% de los asesores activos

**Symptom**: Un análisis de "time to first sale" o "ramp-up" devuelve días absurdos (cualquier asesor "viejo" muestra 2,000-7,000 días entre `FechaIngreso` y su primera venta), aunque para esos asesores los datos de ventas SÍ existen y son recientes. Si lo filtrás como outlier con `--excluir-outliers 365`, **desaparecen 111 de 230 asesores activos**.

**Root cause**: Los datos de ventas / llamadas / leads en el CRM Olympus sólo se registran desde **2026-01-01**. Pero `Personal.FechaIngreso` refleja la contratación real, que en el 48% de los casos es anterior (algunos desde 2005). No es un dato "sucio" — es que el sistema arrancó después.

**Fix (sales mode, default)**: tratá la fecha de ingreso como `MAX(FechaIngreso, SALES_DATA_START)`. Los asesores pre-CRM caen todos en el "cohorte 2026-01-01" con su M1 contando desde esa fecha. La constante `SALES_DATA_START` vive en `lib/queries.py` (y es overridable vía `SALES_DATA_START_DATE` en `.env`).

```python
# lib/queries.py
SALES_DATA_START = os.environ.get("SALES_DATA_START_DATE", "2026-01-01")

def effective_ingreso_expr(hr_mode: bool = False, alias: str = "p.FechaIngreso") -> str:
    if hr_mode:
        return alias
    return f"(CASE WHEN {alias} > '{SALES_DATA_START}' THEN {alias} ELSE CAST('{SALES_DATA_START}' AS date) END)"
```

`scripts/time_to_first_sale.py` y `scripts/cohort_ramp.py` usan sales-mode por default.

**HR mode (`--hr-mode`)**: para tenure / rotación / "cuánto duran los talentos nuevos", usar la `FechaIngreso` real. Pasar el flag a esos dos scripts.

**Decisión rápida**:
- "¿Cuánto tarda un asesor nuevo en cerrar su primera venta?" → sales mode (default).
- "¿Cuál es la rotación promedio?" / "¿Qué % se va antes del año?" → HR mode.
- Cuando reportes TTFS, **siempre indicá qué modo usaste** y mostrá ambas columnas (real y efectiva) para que el lector pueda interpretarlas.

---

## P14. Hardcoding column names from intuition

**Symptom**: Query fails with "Invalid column name 'IdOportunidad'" or "Invalid column name 'IdTipo'".

**Root cause**:
- `Oportunidad.Id` (not `IdOportunidad`)
- `Personal.IdTipoJornada` (not `IdTipo`)
- `HistorialEstado.IdPersonal` (not `IdAsesor`)
- `Oportunidad` is referenced via `IdOportunidad` in `HistorialEstado` and `CobranzaPlan`, but the PK on Oportunidad itself is just `Id`.

**Fix**: read `schema.md` before writing a query. Don't guess column names from analogous tables.

## P16. `Producto.PersonalCreacion` (encargado del curso) tiene NULL + ids huérfanos de prueba

**Symptom**: Un reporte de rentabilidad por "encargado / persona de desarrollo" muestra una fila "(sin nombre)" enorme, o encargados cuyo `Id` no resuelve a ningún nombre.

**Root cause**: `Producto.PersonalCreacion` es la clave del encargado del producto, pero está sucia:
- ~60 productos activos lo tienen `NULL` (sin encargado asignado).
- Hay `PersonalCreacion` que **no existen en `adm.Personal`** (datos de prueba — confirmados los ids **165 y 218**). `SELECT * FROM adm.Personal WHERE Id IN (165,218)` devuelve 0 filas.
- Una sola persona (Patrick Ramírez) figura en ~78 productos: válido, pero el campo es en parte "creador del registro", no siempre el desarrollador real. Interpretar con cuidado al evaluar desempeño individual.

**Fix**: `INNER JOIN adm.Personal per ON per.Id = pr.PersonalCreacion` — descarta NULL y huérfanos en un solo paso. Es lo que hace `rentabilidad_encargado.py`. No uses `LEFT JOIN` para esto salvo que quieras auditar la basura.

## P17. Docente fijo cargado a cohortes sin matrículas (docentes fantasma)

**Symptom**: En un reporte de rentabilidad multi-producto, encargados con muchos productos salen masivamente en rojo aunque vendan bien.

**Root cause**: El costo docente ($1440 ≈ 5.443 PEN) es **por cohorte dictada**. Si lo cargas a cada producto activo —incluyendo pilotos/preventa con 0 matrículas— un dueño de 78 productos acumula ~425K PEN de docente irreal y su margen se desploma artificialmente.

**Fix**: en agregados multi-producto, condiciona el docente a `Matric > 0` (la cohorte efectivamente se dictó). `producto_pnl.py` no necesita esto porque opera sobre un producto puntual que sí se dictó; `rentabilidad_encargado.py` ya aplica el condicional.

---

## P18. `SUM(CASE WHEN (subquery) ...)` — "Cannot perform an aggregate function on an expression containing an aggregate or a subquery"

**Symptom**: Al contar matrículas por grupo metiendo un `EXISTS`/subquery escalar dentro de un `SUM(CASE WHEN ...)`, SQL Server falla con error 130: *"Cannot perform an aggregate function on an expression containing an aggregate or a subquery."*

```sql
-- ❌ Falla
SELECT o.Origen, COUNT(*) AS Leads,
  SUM(CASE WHEN EXISTS (SELECT 1 FROM adm.HistorialEstado h
       WHERE h.IdOportunidad = o.Id AND h.IdEstado = 3) THEN 1 ELSE 0 END) AS Matriculas
FROM adm.Oportunidad o WHERE o.Estado = 1 GROUP BY o.Origen
```

**Root cause**: SQL Server no permite subqueries correlacionadas dentro de una función de agregación.

**Fix**: pre-materializa el set "won" con un `LEFT JOIN` a un subquery `DISTINCT` y cuenta sobre la columna del join:

```sql
-- ✅ Funciona
SELECT o.Origen, COUNT(*) AS Leads,
  SUM(CASE WHEN w.IdOportunidad IS NULL THEN 0 ELSE 1 END) AS Matriculas
FROM adm.Oportunidad o
LEFT JOIN (SELECT DISTINCT IdOportunidad FROM adm.HistorialEstado
           WHERE IdEstado = 3 AND Estado = 1) w ON w.IdOportunidad = o.Id
WHERE o.Estado = 1 GROUP BY o.Origen
```

`conversion_por_origen.py` / `queries.sql_conversion_por_origen` ya lo hacen así.

---

## P19. Comparar TC entre orígenes sin ajustar por intención

**Symptom**: La TC por `Origen` muestra `Manual` 42% y `FormularioWeb` 62% vs `Linkedin` 0,33%, y se concluye "LinkedIn convierte pésimo, cortarlo".

**Root cause**: Los orígenes **no son comparables a igualdad de intención**. `Manual` lo crea el asesor cuando el lead ya está caliente (sesgo de selección → TC inflada); `FormularioWeb`/`Wordpress` son inbound de alta intención y muestra minúscula (n=39 → Wilson LB cae a ~46%); `Linkedin` es lead-gen frío y masivo, pero con su 0,33% sobre 266K leads **aporta >50% de las matrículas absolutas**. La TC sola engaña.

**Fix**: (1) siempre reportar Wilson LB + tamaño de muestra (P13); (2) para decisiones de presupuesto, cruzar con costo (CPL × leads) → **costo por matrícula**, no quedarse en la TC; (3) explicitar el caveat de intención. `conversion_por_origen.py` reporta Leads + Matrículas + TC% + WilsonLB% + %MatricTotal por eso.
