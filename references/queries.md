# Olympus CRM — Query templates

These are battle-tested SQL templates for the most common analytical questions. Each is verified against the live MCP.

Convention: replace `{periodo}` with the number of days (e.g., `30`) or use `'2000-01-01'` for "all time". Replace `{producto_id}`, `{asesor_id}`, etc. with literal values.

## Table of contents

1. Catalog: active asesores
2. Catalog: encargados de producto
3. Leads asignados por asesor en período
4. Llamadas hechas por asesor (delta)
5. Estado actual de cada lead, agregado por asesor
6. Matriculaciones por asesor en período
7. Cobranza comprometida y cobrada por asesor
8. Serie diaria de llamadas (timeseries)
9. Tiempo a primer contacto (velocity)
10. Matriz de transiciones por etapa
11. Leads por país (vía PotencialCliente)
12. Matriculaciones por país
13. Días entre `FechaIngreso` y primera venta del asesor
14. Mejor hora del día para llamar
15. Costos de procesamiento por producto (FTE atribuidos)
16. Detalle de un producto específico
17. Conversión (TC) por origen del lead
18. Campañas de LinkedIn por `FormName` (naming pattern)

---

## 1. Catálogo de asesores activos

```sql
SELECT
  p.Id,
  REPLACE(LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))), ',', '~~') AS Nombre,
  p.IdTipoJornada,
  REPLACE(ISNULL(pa.Nombre,''), ',', '~~') AS Pais,
  p.FechaIngreso
FROM adm.Personal p
LEFT JOIN mdm.Pais pa ON pa.Id = p.IdPais
WHERE p.Estado = 1 AND ISNULL(p.Cesado, 0) = 0 AND p.IdTipoJornada IN (31, 32);
```

## 2. Catálogo de encargados de producto

```sql
SELECT
  pr.PersonalCreacion AS Id,
  REPLACE(LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))), ',', '~~') AS Nombre,
  COUNT(*) AS NumProductos
FROM adm.Producto pr
INNER JOIN adm.Personal p ON p.Id = pr.PersonalCreacion AND p.Estado = 1
WHERE pr.Estado = 1
GROUP BY pr.PersonalCreacion, p.Nombres, p.Apellidos;
```

## 3. Leads asignados por asesor en período

"Primera aparición de cada Oportunidad con ese IdPersonal" = lead asignado.

```sql
SELECT q.IdPersonal, COUNT(*) AS LeadsAsignados
FROM (
  SELECT he.IdPersonal, he.IdOportunidad, he.FechaCreacion,
    ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad, he.IdPersonal ORDER BY he.FechaCreacion, he.Id) AS rn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
) q
WHERE q.rn = 1 AND q.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
GROUP BY q.IdPersonal;
```

## 4. Llamadas hechas por asesor (delta de contadores acumulativos)

```sql
SELECT q.IdPersonal,
  SUM(q.dCc) AS Contestadas,
  SUM(q.dCn) AS NoContestadas,
  COUNT(DISTINCT CAST(q.FechaCreacion AS date)) AS DiasActivos
FROM (
  SELECT he.IdPersonal, he.FechaCreacion,
    CASE WHEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCc,
    CASE WHEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
    AND he.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
) q
GROUP BY q.IdPersonal;
```

## 5. Estado actual de cada lead, agregado por asesor

```sql
SELECT q.IdPersonal, q.IdEstado, COUNT(*) AS LeadsActuales
FROM (
  SELECT he.IdPersonal, he.IdEstado,
    ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion DESC, he.Id DESC) AS rn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
) q
WHERE q.rn = 1
GROUP BY q.IdPersonal, q.IdEstado;
```

## 6. Matriculaciones por asesor en período

Atribuido al asesor de la fila donde `IdEstado=3`.

```sql
SELECT he.IdPersonal, COUNT(DISTINCT he.IdOportunidad) AS Matriculas
FROM adm.HistorialEstado he
WHERE he.Estado = 1 AND he.IdEstado = 3 AND he.IdPersonal IS NOT NULL
  AND he.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
GROUP BY he.IdPersonal;
```

## 7. Cobranza por asesor

```sql
-- Comprometido (CobranzaPlan.Total)
SELECT q.IdPersonal, SUM(cp.Total) AS Comprometido
FROM (
  SELECT he.IdPersonal, he.IdOportunidad
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdEstado = 3 AND he.IdPersonal IS NOT NULL
    AND he.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
  GROUP BY he.IdPersonal, he.IdOportunidad
) q
INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = q.IdOportunidad AND cp.Estado = 1
GROUP BY q.IdPersonal;
```

```sql
-- Cobrado (CobranzaPago.Monto)
SELECT he.IdPersonal, SUM(pago.Monto) AS Cobrado
FROM adm.HistorialEstado he
INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = he.IdOportunidad AND cp.Estado = 1
INNER JOIN adm.CobranzaPago pago ON pago.IdCobranzaPlan = cp.Id AND pago.Estado = 1
WHERE he.Estado = 1 AND he.IdEstado = 3 AND he.IdPersonal IS NOT NULL
  AND he.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
GROUP BY he.IdPersonal;
```

## 8. Serie diaria de llamadas (global)

```sql
SELECT CAST(q.FechaCreacion AS date) AS Dia,
  SUM(q.dCc) AS Contestadas,
  SUM(q.dCn) AS NoContestadas
FROM (
  SELECT he.FechaCreacion,
    CASE WHEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCc,
    CASE WHEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
    AND he.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
) q
GROUP BY CAST(q.FechaCreacion AS date);
```

## 9. Tiempo a primer contacto

**Don't use `CantidadLlamadas > 0`** — the first row already has counts. Use the second row by chronological order.

```sql
SELECT op.Id AS IdOportunidad, fc.IdPersonal,
  DATEDIFF(minute, op.FechaCreacion, fc.PrimerTrabajo) AS Minutos
FROM adm.Oportunidad op
INNER JOIN (
  SELECT IdOportunidad, IdPersonal, FechaCreacion AS PrimerTrabajo
  FROM (
    SELECT IdOportunidad, IdPersonal, FechaCreacion,
      ROW_NUMBER() OVER (PARTITION BY IdOportunidad ORDER BY FechaCreacion, Id) AS rn
    FROM adm.HistorialEstado WHERE Estado = 1
  ) z WHERE rn = 2
) fc ON fc.IdOportunidad = op.Id
WHERE op.Estado = 1
  AND op.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
  AND DATEDIFF(minute, op.FechaCreacion, fc.PrimerTrabajo) BETWEEN 0 AND 525600;
```

## 10. Matriz de transiciones por asesor

```sql
SELECT q.IdPersonal, q.EstadoOrigen, q.EstadoDestino, COUNT(*) AS N
FROM (
  SELECT he.IdPersonal,
    LAG(he.IdEstado) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id) AS EstadoOrigen,
    he.IdEstado AS EstadoDestino
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1
    AND he.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
) q
WHERE q.IdPersonal IS NOT NULL
  AND q.EstadoOrigen IS NOT NULL
  AND q.EstadoOrigen <> q.EstadoDestino
  AND q.EstadoOrigen IN (1, 4, 5, 6)
  AND q.EstadoDestino IN (3, 4, 5, 6, 7)
GROUP BY q.IdPersonal, q.EstadoOrigen, q.EstadoDestino;
```

Compute funnel as: `Reg → Cal+` = (transitions where origen=1, destino ∈ {4,5,6,3}) / (all transitions from origen=1).

## 11. Leads por país (CRITICAL: vía PotencialCliente)

```sql
SELECT pa.Nombre AS Pais, COUNT(*) AS Leads
FROM adm.Oportunidad op
INNER JOIN adm.Producto pr        ON pr.Id  = op.IdProducto AND pr.Estado = 1
INNER JOIN adm.PotencialCliente pc ON pc.Id = op.IdPotencialCliente
INNER JOIN adm.Persona per         ON per.Id = pc.IdPersona
INNER JOIN mdm.Pais pa             ON pa.Id  = per.IdPais
WHERE op.Estado = 1
  AND (pr.Nombre LIKE '%antenimiento%' OR pr.Nombre LIKE '%inanzas%')  -- filtro de tema
GROUP BY pa.Nombre;
```

Replace the topic filter with whatever subset of products you care about.

## 12. Matriculaciones por país

```sql
SELECT pa.Nombre AS Pais, COUNT(DISTINCT h.IdOportunidad) AS Matriculados
FROM adm.HistorialEstado h
INNER JOIN adm.Oportunidad op       ON op.Id = h.IdOportunidad AND op.Estado = 1
INNER JOIN adm.Producto pr          ON pr.Id = op.IdProducto AND pr.Estado = 1
INNER JOIN adm.PotencialCliente pc  ON pc.Id = op.IdPotencialCliente
INNER JOIN adm.Persona per          ON per.Id = pc.IdPersona
INNER JOIN mdm.Pais pa              ON pa.Id = per.IdPais
WHERE h.Estado = 1 AND h.IdEstado = 3
  AND (pr.Nombre LIKE '%antenimiento%' OR pr.Nombre LIKE '%inanzas%')
GROUP BY pa.Nombre;
```

## 13. Días entre `FechaIngreso` y primera venta del asesor

Two variants depending on attribution rule:

**A) Primera venta = primera matriculación que el asesor MOVIÓ a estado 3 (`HistorialEstado.IdPersonal`):**

```sql
SELECT
  REPLACE(LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))), ',', '~~') AS Nombre,
  p.FechaIngreso,
  v.FechaPrimeraVenta,
  DATEDIFF(day, p.FechaIngreso, v.FechaPrimeraVenta) AS DiferenciaDias
FROM adm.Personal p
INNER JOIN (
  SELECT he.IdPersonal, MIN(he.FechaCreacion) AS FechaPrimeraVenta
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdEstado = 3 AND he.IdPersonal IS NOT NULL
  GROUP BY he.IdPersonal
) v ON v.IdPersonal = p.Id
WHERE p.Estado = 1
  AND p.FechaIngreso IS NOT NULL
  AND DATEDIFF(day, p.FechaIngreso, v.FechaPrimeraVenta) >= 0
ORDER BY DiferenciaDias;
```

**B) Primera venta = primera oportunidad que el asesor "owns" (`Oportunidad.IdPersonal`) que llegó a estado 3:**

```sql
SELECT
  REPLACE(LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))), ',', '~~') AS Nombre,
  p.FechaIngreso,
  v.PrimeraVenta AS FechaPrimeraVenta,
  DATEDIFF(day, p.FechaIngreso, v.PrimeraVenta) AS DiferenciaDias
FROM adm.Personal p
INNER JOIN (
  SELECT op.IdPersonal, MIN(h.FechaCreacion) AS PrimeraVenta
  FROM adm.HistorialEstado h
  INNER JOIN adm.Oportunidad op ON op.Id = h.IdOportunidad AND op.Estado = 1
  WHERE h.Estado = 1 AND h.IdEstado = 3 AND op.IdPersonal IS NOT NULL
  GROUP BY op.IdPersonal
) v ON v.IdPersonal = p.Id
WHERE p.Estado = 1
  AND p.FechaIngreso IS NOT NULL
  AND DATEDIFF(day, p.FechaIngreso, v.PrimeraVenta) >= 0
ORDER BY DiferenciaDias;
```

Variant B is more aligned with the org's "asignación" model; variant A credits the actual closer. Ask the user which they prefer if it matters.

**Always exclude `DiferenciaDias > 365`** as outliers — those are asesores with pre-CRM history (`FechaIngreso` from 2005 / 2001, etc.).

## 14. Mejor hora del día para llamar

```sql
SELECT DATEPART(hour, q.FechaCreacion) AS Hora,
  SUM(q.dCc) AS Contestadas,
  SUM(q.dCn) AS NoContestadas,
  SUM(q.dCc + q.dCn) AS Total
FROM (
  -- (same delta subquery as query 4)
  SELECT he.FechaCreacion,
    CASE WHEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasContestadas
           - ISNULL(LAG(he.CantidadLlamadasContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCc,
    CASE WHEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0) > 0
         THEN he.CantidadLlamadasNoContestadas
           - ISNULL(LAG(he.CantidadLlamadasNoContestadas) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)
         ELSE 0 END AS dCn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
    AND he.FechaCreacion >= DATEADD(day, -{periodo}, CAST(GETDATE() AS date))
) q
GROUP BY DATEPART(hour, q.FechaCreacion);
```

Best window = hour with highest `Contestadas / Total` AND volume above a minimum threshold (e.g., ≥5% of peak).

## 15. Costos de procesamiento por producto — FTE atribuidos

Step 1: leads del asesor en el producto:
```sql
SELECT he.IdPersonal, COUNT(DISTINCT he.IdOportunidad) AS LeadsProducto
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1 AND op.IdProducto = {producto_id}
WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
GROUP BY he.IdPersonal;
```

Step 2: leads totales del asesor en el mismo período (para el ratio):
```sql
SELECT he.IdPersonal, COUNT(DISTINCT he.IdOportunidad) AS LeadsTotal
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
GROUP BY he.IdPersonal;
```

Combinar en cliente: para cada asesor, `peso = leadsProducto / leadsTotal`. Sumar pesos = FTE equivalents. Costo salarial atribuido = `salarioBasePEN × sum(pesos)`.

## 16. Detalle de un producto específico (KPIs)

```sql
SELECT
  (SELECT COUNT(DISTINCT op.Id)
     FROM adm.Oportunidad op
     INNER JOIN adm.HistorialEstado he ON he.IdOportunidad = op.Id AND he.Estado = 1 AND he.IdPersonal IS NOT NULL
     WHERE op.IdProducto = {producto_id} AND op.Estado = 1) AS TotalLeads,
  (SELECT COUNT(DISTINCT he.IdPersonal)
     FROM adm.HistorialEstado he
     INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
     WHERE op.IdProducto = {producto_id} AND he.Estado = 1 AND he.IdPersonal IS NOT NULL) AS AsesoresInvolucrados,
  (SELECT COUNT(DISTINCT h.IdOportunidad)
     FROM adm.HistorialEstado h
     INNER JOIN adm.Oportunidad o ON o.Id = h.IdOportunidad AND o.Estado = 1
     WHERE o.IdProducto = {producto_id} AND h.Estado = 1 AND h.IdEstado = 3) AS Matriculados,
  (SELECT SUM(cp.Total)
     FROM adm.CobranzaPlan cp
     INNER JOIN adm.Oportunidad o ON o.Id = cp.IdOportunidad
     WHERE o.IdProducto = {producto_id} AND o.Estado = 1 AND cp.Estado = 1) AS MontoComprometidoUSD,
  (SELECT SUM(pago.Monto)
     FROM adm.CobranzaPago pago
     INNER JOIN adm.CobranzaPlan cp ON cp.Id = pago.IdCobranzaPlan
     INNER JOIN adm.Oportunidad o ON o.Id = cp.IdOportunidad
     WHERE o.IdProducto = {producto_id} AND o.Estado = 1 AND cp.Estado = 1 AND pago.Estado = 1) AS MontoCobradoUSD;
```

If this composite query times out via the MCP, split into 5 separate queries and combine results in the client.

## 17. Conversión (TC) por origen del lead

Compara el canal de captación (`Oportunidad.Origen`). Convertido = alcanzó estado
Matriculado. **No** uses un subquery dentro del `SUM(CASE ...)` (error 130 — ver
pitfall P18); usa `LEFT JOIN` a un set `DISTINCT` de won. Calcula Wilson LB en el
cliente (muestras muy dispares). Prefiere `conversion_por_origen.py`.

```sql
SELECT ISNULL(o.Origen, '(NULL)') AS Origen,
       COUNT(*) AS Leads,
       SUM(CASE WHEN w.IdOportunidad IS NULL THEN 0 ELSE 1 END) AS Matriculas
FROM adm.Oportunidad o
LEFT JOIN (SELECT DISTINCT IdOportunidad FROM adm.HistorialEstado
           WHERE IdEstado = 3 AND Estado = 1) w ON w.IdOportunidad = o.Id
WHERE o.Estado = 1
GROUP BY o.Origen;
```

Caveat: las TC entre orígenes no son comparables a igualdad de intención (P19).

## 18. Campañas de LinkedIn por `FormName` (naming pattern)

`FormName` es el único detalle de campaña (`Oportunidad.Origen` sólo dice `Linkedin`).
Patrón: `[FOR-]<FORMATO><TEMA>[NIVEL][SEGMENTO]`, FORMATO ∈ {PAE,CEP,PEP,PAD}.
`adm.LinkedIn_Lead` no tiene `Estado`; `TestLead=1` son pruebas. Prefiere
`linkedin_campanas.py` (parsea el patrón en columnas).

```sql
-- Listado / búsqueda (poné el filtro que necesites)
SELECT FormName, COUNT(*) AS Leads,
       CONVERT(varchar(10), MIN(CreatedDate), 23) AS Primera,
       CONVERT(varchar(10), MAX(CreatedDate), 23) AS Ultima
FROM adm.LinkedIn_Lead
WHERE FormName IS NOT NULL
  -- AND FormName LIKE '%Doc%'        -- buscar texto
  -- AND ISNULL(TestLead, 0) = 0      -- excluir leads de prueba
GROUP BY FormName
ORDER BY Leads DESC;

-- Agregado por formato (PAE/CEP/PEP/PAD vs ad-hoc), quitando el prefijo FOR-
SELECT LEFT(CASE WHEN FormName LIKE 'FOR-%' THEN SUBSTRING(FormName, 5, 200)
                 ELSE FormName END, 3) AS Formato,
       COUNT(DISTINCT FormName) AS Campanas, COUNT(*) AS Leads
FROM adm.LinkedIn_Lead
WHERE FormName IS NOT NULL
GROUP BY LEFT(CASE WHEN FormName LIKE 'FOR-%' THEN SUBSTRING(FormName, 5, 200)
                   ELSE FormName END, 3)
ORDER BY Leads DESC;
```
