"""
SQL query templates as Python strings. Centralized so all scripts share them.

Each function returns a SQL string with `?` placeholders (pyodbc parameter style).
"""
from __future__ import annotations

import os
import re

# ──────────────────────────────────────────────────────────────────────────
# Sales-data effective start.
#
# The CRM only started recording ventas/llamadas/leads on 2026-01-01, but
# `Personal.FechaIngreso` for ~48% of active asesores is much earlier
# (some go back to 2005). For sales analyses (TTFS, ramp-up, cohort),
# treat the effective hire date as MAX(FechaIngreso, SALES_DATA_START).
# For HR analyses (rotación, tenure), use the raw FechaIngreso — opt-in
# via the `hr_mode=True` flag wherever a query supports it.
#
# Configurable via env var SALES_DATA_START_DATE (default 2026-01-01).
# ──────────────────────────────────────────────────────────────────────────

SALES_DATA_START = os.environ.get("SALES_DATA_START_DATE")
if SALES_DATA_START is None:
    SALES_DATA_START = "2026-01-01"
    import sys as _sys
    print(
        f"AVISO: SALES_DATA_START_DATE no está en .env; usando default {SALES_DATA_START} "
        "(análisis TTFS/cohort/ramp-up dependen de esta fecha).",
        file=_sys.stderr,
    )

# Defensive: only accept ISO date strings so we can safely interpolate into SQL.
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", SALES_DATA_START):
    raise ValueError(
        f"SALES_DATA_START_DATE debe ser YYYY-MM-DD, recibido: {SALES_DATA_START!r}"
    )


def effective_ingreso_expr(hr_mode: bool = False, alias: str = "p.FechaIngreso") -> str:
    """
    SQL expression for the asesor's *effective* hire date.

    - hr_mode=False (default, sales mode): MAX(FechaIngreso, SALES_DATA_START).
    - hr_mode=True: raw column reference (for tenure / rotación analyses).
    """
    if hr_mode:
        return alias
    return (
        f"(CASE WHEN {alias} > '{SALES_DATA_START}' "
        f"THEN {alias} ELSE CAST('{SALES_DATA_START}' AS date) END)"
    )


def fecha_filter(days: int | None) -> tuple[str, list]:
    """Returns (predicate, params). If days is None -> all time."""
    if days is None:
        return ("'2000-01-01'", [])
    return ("DATEADD(day, -?, CAST(GETDATE() AS date))", [days])


def sql_filtrar_asesor(sql: str) -> str:
    """
    Envuelve una query agregada por asesor (debe exponer columna IdPersonal)
    para filtrar UN solo asesor en el servidor, en vez de traer todos los
    asesores y filtrar en Python. Agrega un parámetro `?` AL FINAL de los
    params de la query original: el IdPersonal.
    """
    return f"SELECT * FROM (\n{sql}\n) t WHERE t.IdPersonal = ?"


def matricula_evento(alias: str = "he") -> str:
    """
    Predicado canónico de "evento de matrícula" en HistorialEstado: fila viva
    (Estado=1, soft-delete) que llegó a estado Matriculado (IdEstado=3).
    El dedup por oportunidad se hace aparte (COUNT(DISTINCT IdOportunidad) o
    SELECT DISTINCT), porque una oportunidad puede tener varias filas en 3.
    ÚNICA fuente de esta regla — si cambia el enum de estados, tocar solo aquí.
    """
    return f"{alias}.Estado = 1 AND {alias}.IdEstado = 3"


def sql_llamadas_delta(select_cols: str, where: str) -> str:
    """
    Subconsulta con el delta REAL de llamadas por fila de HistorialEstado.
    Los contadores CantidadLlamadas* son ACUMULATIVOS por oportunidad: el delta
    es fila − LAG(fila) sobre la misma oportunidad, con negativos clampados a 0
    (los contadores a veces se resetean). ÚNICA fuente del patrón — antes vivía
    copiado en 4 sitios.

    select_cols: columnas de he.* a exponer junto a dCc/dCn.
    where: predicado adicional con placeholders `?` (se ANDea a he.Estado=1).
    """
    def _delta(col: str) -> str:
        lag = (f"ISNULL(LAG(he.{col}) OVER "
               f"(PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id), 0)")
        return f"CASE WHEN he.{col} - {lag} > 0 THEN he.{col} - {lag} ELSE 0 END"

    return f"""
  SELECT {select_cols},
    {_delta("CantidadLlamadasContestadas")} AS dCc,
    {_delta("CantidadLlamadasNoContestadas")} AS dCn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND {where}
"""


# Catalog
SQL_ASESORES_ACTIVOS = """
SELECT
  p.Id,
  LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))) AS Nombre,
  p.IdTipoJornada AS Jornada,
  ISNULL(pa.Nombre,'') AS Pais,
  p.FechaIngreso
FROM adm.Personal p
LEFT JOIN mdm.Pais pa ON pa.Id = p.IdPais
WHERE p.Estado = 1 AND ISNULL(p.Cesado, 0) = 0 AND p.IdTipoJornada IN (31, 32)
"""

# Leads asignados por asesor
SQL_LEADS_ASIGNADOS = """
SELECT q.IdPersonal, COUNT(*) AS LeadsAsignados
FROM (
  SELECT he.IdPersonal, he.IdOportunidad, he.FechaCreacion,
    ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad, he.IdPersonal ORDER BY he.FechaCreacion, he.Id) AS rn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
) q
WHERE q.rn = 1 AND q.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
GROUP BY q.IdPersonal
"""

# Llamadas por asesor (delta + días activos)
SQL_LLAMADAS_POR_ASESOR = f"""
SELECT q.IdPersonal,
  SUM(q.dCc) AS Contestadas,
  SUM(q.dCn) AS NoContestadas,
  COUNT(DISTINCT CAST(q.FechaCreacion AS date)) AS DiasActivos
FROM ({sql_llamadas_delta(
    "he.IdPersonal, he.FechaCreacion",
    "he.IdPersonal IS NOT NULL AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))",
)}) q
GROUP BY q.IdPersonal
"""

# Matriculaciones por asesor
SQL_MATRICULAS_POR_ASESOR = f"""
SELECT he.IdPersonal, COUNT(DISTINCT he.IdOportunidad) AS Matriculas
FROM adm.HistorialEstado he
WHERE {matricula_evento()} AND he.IdPersonal IS NOT NULL
  AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
GROUP BY he.IdPersonal
"""

# Cobranza comprometida por asesor
SQL_COBRANZA_COMPROMETIDA = f"""
SELECT q.IdPersonal, SUM(cp.Total) AS ComprometidoUSD
FROM (
  SELECT he.IdPersonal, he.IdOportunidad
  FROM adm.HistorialEstado he
  WHERE {matricula_evento()} AND he.IdPersonal IS NOT NULL
    AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
  GROUP BY he.IdPersonal, he.IdOportunidad
) q
INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = q.IdOportunidad AND cp.Estado = 1
GROUP BY q.IdPersonal
"""

# Cobranza cobrada por asesor
SQL_COBRANZA_COBRADA = f"""
SELECT he.IdPersonal, SUM(pago.Monto) AS CobradoUSD
FROM adm.HistorialEstado he
INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = he.IdOportunidad AND cp.Estado = 1
INNER JOIN adm.CobranzaPago pago ON pago.IdCobranzaPlan = cp.Id AND pago.Estado = 1
WHERE {matricula_evento()} AND he.IdPersonal IS NOT NULL
  AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
GROUP BY he.IdPersonal
"""

# Tiempo a primer contacto (rn=2)
SQL_VELOCITY = """
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
  AND op.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
  AND DATEDIFF(minute, op.FechaCreacion, fc.PrimerTrabajo) BETWEEN 0 AND 525600
"""

# Llamadas por hora del día
SQL_CALLS_BY_HOUR = f"""
SELECT DATEPART(hour, q.FechaCreacion) AS Hora,
  SUM(q.dCc) AS Contestadas,
  SUM(q.dCn) AS NoContestadas,
  SUM(q.dCc + q.dCn) AS Total
FROM ({sql_llamadas_delta(
    "he.FechaCreacion, he.IdPersonal",
    "he.IdPersonal IS NOT NULL AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))",
)}) q
GROUP BY DATEPART(hour, q.FechaCreacion)
"""

# Transiciones por asesor
SQL_TRANSICIONES = """
SELECT q.IdPersonal, q.EstadoOrigen, q.EstadoDestino, COUNT(*) AS N
FROM (
  SELECT he.IdPersonal,
    LAG(he.IdEstado) OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion, he.Id) AS EstadoOrigen,
    he.IdEstado AS EstadoDestino
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1
    AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
) q
WHERE q.IdPersonal IS NOT NULL AND q.EstadoOrigen IS NOT NULL AND q.EstadoOrigen <> q.EstadoDestino
  AND q.EstadoOrigen IN (1, 4, 5, 6) AND q.EstadoDestino IN (3, 4, 5, 6, 7)
GROUP BY q.IdPersonal, q.EstadoOrigen, q.EstadoDestino
"""

# Leads por país (vía PotencialCliente). Param: filtro de nombre LIKE (pasar '%' para todos)
SQL_LEADS_POR_PAIS = """
SELECT pa.Nombre AS Pais, COUNT(*) AS Leads
FROM adm.Oportunidad op
INNER JOIN adm.Producto pr        ON pr.Id  = op.IdProducto AND pr.Estado = 1
INNER JOIN adm.PotencialCliente pc ON pc.Id = op.IdPotencialCliente
INNER JOIN adm.Persona per         ON per.Id = pc.IdPersona
INNER JOIN mdm.Pais pa             ON pa.Id  = per.IdPais
WHERE op.Estado = 1
  AND pr.Nombre LIKE ?
GROUP BY pa.Nombre
"""

# Matriculados por país
SQL_MATRIC_POR_PAIS = f"""
SELECT pa.Nombre AS Pais, COUNT(DISTINCT h.IdOportunidad) AS Matriculados
FROM adm.HistorialEstado h
INNER JOIN adm.Oportunidad op       ON op.Id = h.IdOportunidad AND op.Estado = 1
INNER JOIN adm.Producto pr          ON pr.Id = op.IdProducto AND pr.Estado = 1
INNER JOIN adm.PotencialCliente pc  ON pc.Id = op.IdPotencialCliente
INNER JOIN adm.Persona per          ON per.Id = pc.IdPersona
INNER JOIN mdm.Pais pa              ON pa.Id = per.IdPais
WHERE {matricula_evento('h')}
  AND pr.Nombre LIKE ?
GROUP BY pa.Nombre
"""

# Días entre FechaIngreso (efectiva o real, según hr_mode) y primera venta.
# Atribución de venta vía Oportunidad.IdPersonal (asesor "owner" actual del lead).
def sql_time_to_first_sale(hr_mode: bool = False) -> str:
    ingreso = effective_ingreso_expr(hr_mode)
    return f"""
SELECT
  p.Id,
  LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))) AS Nombre,
  CONVERT(varchar(10), p.FechaIngreso, 23)   AS FechaIngresoReal,
  CONVERT(varchar(10), {ingreso}, 23)        AS FechaIngresoEfectiva,
  CONVERT(varchar(10), v.PrimeraVenta, 23)   AS FechaPrimeraVenta,
  DATEDIFF(day, {ingreso}, v.PrimeraVenta)   AS DiferenciaDias
FROM adm.Personal p
INNER JOIN (
  SELECT op.IdPersonal, MIN(h.FechaCreacion) AS PrimeraVenta
  FROM adm.HistorialEstado h
  INNER JOIN adm.Oportunidad op ON op.Id = h.IdOportunidad AND op.Estado = 1
  WHERE {matricula_evento('h')} AND op.IdPersonal IS NOT NULL
  GROUP BY op.IdPersonal
) v ON v.IdPersonal = p.Id
WHERE p.Estado = 1
  AND ISNULL(p.Cesado, 0) = 0
  AND p.FechaIngreso IS NOT NULL
  AND {ingreso} >= ?
  AND DATEDIFF(day, {ingreso}, v.PrimeraVenta) >= 0
"""

# Búsqueda de productos
SQL_PRODUCT_SEARCH = """
SELECT pr.Id, pr.Nombre, pr.CodigoLanzamiento, pr.CostoBase, pr.EstadoProductoTipoId,
  CONVERT(varchar(10), pr.FechaInicio, 23) AS FechaInicio
FROM adm.Producto pr
WHERE pr.Estado = 1
  AND (pr.Nombre LIKE ? OR pr.CodigoLanzamiento LIKE ?)
ORDER BY pr.Id DESC
"""

# KPIs de un producto específico
SQL_PRODUCT_KPIS = f"""
SELECT
  (SELECT COUNT(DISTINCT op.Id)
     FROM adm.Oportunidad op
     INNER JOIN adm.HistorialEstado he ON he.IdOportunidad = op.Id AND he.Estado = 1 AND he.IdPersonal IS NOT NULL
     WHERE op.IdProducto = ? AND op.Estado = 1) AS TotalLeads,
  (SELECT COUNT(DISTINCT he.IdPersonal)
     FROM adm.HistorialEstado he
     INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
     WHERE op.IdProducto = ? AND he.Estado = 1 AND he.IdPersonal IS NOT NULL) AS AsesoresInvolucrados,
  (SELECT COUNT(DISTINCT h.IdOportunidad)
     FROM adm.HistorialEstado h
     INNER JOIN adm.Oportunidad o ON o.Id = h.IdOportunidad AND o.Estado = 1
     WHERE o.IdProducto = ? AND {matricula_evento('h')}) AS Matriculados,
  (SELECT SUM(cp.Total)
     FROM adm.CobranzaPlan cp
     INNER JOIN adm.Oportunidad o ON o.Id = cp.IdOportunidad
     WHERE o.IdProducto = ? AND o.Estado = 1 AND cp.Estado = 1) AS MontoComprometidoUSD,
  (SELECT SUM(pago.Monto)
     FROM adm.CobranzaPago pago
     INNER JOIN adm.CobranzaPlan cp ON cp.Id = pago.IdCobranzaPlan
     INNER JOIN adm.Oportunidad o ON o.Id = cp.IdOportunidad
     WHERE o.IdProducto = ? AND o.Estado = 1 AND cp.Estado = 1 AND pago.Estado = 1) AS MontoCobradoUSD,
  (SELECT pr.CostoBase FROM adm.Producto pr WHERE pr.Id = ?) AS CostoBaseUSD,
  (SELECT pr.Nombre FROM adm.Producto pr WHERE pr.Id = ?) AS Nombre
"""

# ────────────────────────────────────────────────────────────────────────
# Estado ACTUAL del funnel: por cada oportunidad, su estado vigente = la
# última fila de HistorialEstado (por FechaCreacion DESC, Id DESC). Cuenta
# cuántas oportunidades están HOY en cada estado. Distinto de
# SQL_TRANSICIONES (flujo entre etapas) — esto es la foto del stock actual.
#
# Param: IdProducto. Pasar NULL para global (todos los productos).
# ────────────────────────────────────────────────────────────────────────
SQL_FUNNEL_ESTADO_ACTUAL = """
SELECT cur.IdEstado, COUNT(*) AS N
FROM (
  SELECT he.IdOportunidad, he.IdEstado,
    ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad ORDER BY he.FechaCreacion DESC, he.Id DESC) AS rn
  FROM adm.HistorialEstado he
  INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
    AND (? IS NULL OR op.IdProducto = ?)
  WHERE he.Estado = 1
) cur
WHERE cur.rn = 1
GROUP BY cur.IdEstado
"""

# Leads del producto por asesor (para FTE attribution)
SQL_LEADS_PRODUCTO_POR_ASESOR = """
SELECT he.IdPersonal, COUNT(DISTINCT he.IdOportunidad) AS LeadsProducto
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1 AND op.IdProducto = ?
WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
GROUP BY he.IdPersonal
"""

SQL_LEADS_TOTAL_POR_ASESOR = """
SELECT he.IdPersonal, COUNT(DISTINCT he.IdOportunidad) AS LeadsTotal
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
GROUP BY he.IdPersonal
"""


# Leads por (asesor, producto) — filtrado a un asesor en el período. Params: IdPersonal, days.
SQL_LEADS_ASESOR_X_PRODUCTO = """
SELECT op.IdProducto, pr.Nombre AS Producto,
  COUNT(DISTINCT he.IdOportunidad) AS Leads
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
INNER JOIN adm.Producto pr    ON pr.Id = op.IdProducto AND pr.Estado = 1
WHERE he.Estado = 1 AND he.IdPersonal = ?
  AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
GROUP BY op.IdProducto, pr.Nombre
"""

# Matrículas por (asesor, producto). Params: IdPersonal, days.
SQL_MATRIC_ASESOR_X_PRODUCTO = f"""
SELECT op.IdProducto, COUNT(DISTINCT he.IdOportunidad) AS Matric
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
WHERE {matricula_evento()} AND he.IdPersonal = ?
  AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
GROUP BY op.IdProducto
"""

# Cobrado por (asesor, producto) — sólo oportunidades que el asesor matriculó.
# Params: IdPersonal, days.
SQL_COBRADO_ASESOR_X_PRODUCTO = f"""
SELECT op.IdProducto, SUM(pago.Monto) AS CobradoUSD
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op    ON op.Id = he.IdOportunidad AND op.Estado = 1
INNER JOIN adm.CobranzaPlan cp   ON cp.IdOportunidad = op.Id AND cp.Estado = 1
INNER JOIN adm.CobranzaPago pago ON pago.IdCobranzaPlan = cp.Id AND pago.Estado = 1
WHERE {matricula_evento()} AND he.IdPersonal = ?
  AND he.FechaCreacion >= DATEADD(day, -?, CAST(GETDATE() AS date))
GROUP BY op.IdProducto
"""


# ────────────────────────────────────────────────────────────────────────
# Top de programas por ventas en una ventana de fechas.
#
# Por producto, en la ventana [desde, hasta) (hasta exclusivo):
#   - Ventas        = matrículas (IdEstado=3) cerradas en la ventana (flujo).
#   - Leads         = oportunidades CREADAS en la ventana (cohorte de captación).
#   - ConvCohorte   = de esos leads creados en la ventana, cuántos ya llegaron
#                     a estado 3 alguna vez (numerador limpio para la TC cohorte).
#   - ComprometidoUSD = SUM(CobranzaPlan.Total) de las oportunidades vendidas
#                       en la ventana (dedup por oportunidad).
#   - CobradoUSD    = SUM(CobranzaPago.Monto) de esas mismas oportunidades.
#
# Inline subqueries (no CTE) por compatibilidad con el MCP; el ORDER BY / TOP
# se hace en el cliente. Params (pyodbc, en orden): desde, hasta (una sola vez;
# el DECLARE los propaga a las 5 subconsultas).
# ────────────────────────────────────────────────────────────────────────
SQL_PROGRAMAS_TOP_VENTAS = f"""
DECLARE @desde date = ?, @hasta date = ?;
SELECT pr.Id,
  ISNULL(pr.CodigoLanzamiento, '') AS Codigo,
  pr.Nombre,
  ISNULL(l.Leads, 0)            AS Leads,
  v.Ventas                      AS Ventas,
  ISNULL(c.Conv, 0)             AS ConvCohorte,
  ISNULL(rc.ComprometidoUSD, 0) AS ComprometidoUSD,
  ISNULL(rp.CobradoUSD, 0)      AS CobradoUSD
FROM adm.Producto pr
INNER JOIN (
  SELECT op.IdProducto, COUNT(DISTINCT h.IdOportunidad) AS Ventas
  FROM adm.HistorialEstado h
  INNER JOIN adm.Oportunidad op ON op.Id = h.IdOportunidad AND op.Estado = 1
  WHERE {matricula_evento('h')} AND h.FechaCreacion >= @desde AND h.FechaCreacion < @hasta
  GROUP BY op.IdProducto
) v ON v.IdProducto = pr.Id
LEFT JOIN (
  SELECT op.IdProducto, COUNT(DISTINCT op.Id) AS Leads
  FROM adm.Oportunidad op
  WHERE op.Estado = 1 AND op.FechaCreacion >= @desde AND op.FechaCreacion < @hasta
  GROUP BY op.IdProducto
) l ON l.IdProducto = pr.Id
LEFT JOIN (
  SELECT op.IdProducto, COUNT(DISTINCT op.Id) AS Conv
  FROM adm.Oportunidad op
  INNER JOIN adm.HistorialEstado h ON h.IdOportunidad = op.Id AND {matricula_evento('h')}
  WHERE op.Estado = 1 AND op.FechaCreacion >= @desde AND op.FechaCreacion < @hasta
  GROUP BY op.IdProducto
) c ON c.IdProducto = pr.Id
LEFT JOIN (
  SELECT q.IdProducto, SUM(cp.Total) AS ComprometidoUSD
  FROM (
    SELECT DISTINCT op.IdProducto, op.Id AS IdOportunidad
    FROM adm.HistorialEstado h
    INNER JOIN adm.Oportunidad op ON op.Id = h.IdOportunidad AND op.Estado = 1
    WHERE {matricula_evento('h')} AND h.FechaCreacion >= @desde AND h.FechaCreacion < @hasta
  ) q
  INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = q.IdOportunidad AND cp.Estado = 1
  GROUP BY q.IdProducto
) rc ON rc.IdProducto = pr.Id
LEFT JOIN (
  SELECT q.IdProducto, SUM(pago.Monto) AS CobradoUSD
  FROM (
    SELECT DISTINCT op.IdProducto, op.Id AS IdOportunidad
    FROM adm.HistorialEstado h
    INNER JOIN adm.Oportunidad op ON op.Id = h.IdOportunidad AND op.Estado = 1
    WHERE {matricula_evento('h')} AND h.FechaCreacion >= @desde AND h.FechaCreacion < @hasta
  ) q
  INNER JOIN adm.CobranzaPlan cp   ON cp.IdOportunidad = q.IdOportunidad AND cp.Estado = 1
  INNER JOIN adm.CobranzaPago pago ON pago.IdCobranzaPlan = cp.Id AND pago.Estado = 1
  GROUP BY q.IdProducto
) rp ON rp.IdProducto = pr.Id
WHERE pr.Estado = 1
"""


# ────────────────────────────────────────────────────────────────────────
# Rentabilidad por encargado del producto (Producto.PersonalCreacion).
# INNER JOIN a Personal => excluye productos sin encargado (NULL) y los
# PersonalCreacion huérfanos (ids de prueba que no existen en adm.Personal).
# ────────────────────────────────────────────────────────────────────────

# Productos activos con encargado válido (existe en adm.Personal).
SQL_PRODUCTOS_ENCARGADO = """
SELECT pr.Id, pr.Nombre, pr.PersonalCreacion AS Encargado,
  LTRIM(RTRIM(ISNULL(per.Nombres,'') + ' ' + ISNULL(per.Apellidos,''))) AS EncargadoNombre
FROM adm.Producto pr
INNER JOIN adm.Personal per ON per.Id = pr.PersonalCreacion
WHERE pr.Estado = 1
"""

# Leads y matrículas totales por producto (all-time).
SQL_LEADS_MATRIC_POR_PRODUCTO = """
SELECT op.IdProducto AS P,
  COUNT(DISTINCT op.Id) AS Leads,
  COUNT(DISTINCT CASE WHEN he.IdEstado = 3 THEN he.IdOportunidad END) AS Matric
FROM adm.Oportunidad op
LEFT JOIN adm.HistorialEstado he ON he.IdOportunidad = op.Id AND he.Estado = 1
WHERE op.Estado = 1
GROUP BY op.IdProducto
"""

# Leads (oportunidades CREADAS) por producto en una ventana. Params: desde, hasta (exclusivo).
SQL_LEADS_VENTANA_POR_PRODUCTO = """
SELECT op.IdProducto AS P, COUNT(DISTINCT op.Id) AS LeadsVentana
FROM adm.Oportunidad op
WHERE op.Estado = 1 AND op.FechaCreacion >= @desde AND op.FechaCreacion < @hasta
GROUP BY op.IdProducto
"""

# Cobrado por producto desde una fecha. Param: fecha (YYYY-MM-DD).
SQL_COBRADO_DESDE_POR_PRODUCTO = """
SELECT op.IdProducto AS P, SUM(pago.Monto) AS CobradoUSD
FROM adm.CobranzaPago pago
INNER JOIN adm.CobranzaPlan cp   ON cp.Id = pago.IdCobranzaPlan AND cp.Estado = 1
INNER JOIN adm.Oportunidad op    ON op.Id = cp.IdOportunidad AND op.Estado = 1
WHERE pago.Estado = 1 AND pago.FechaPago >= ?
GROUP BY op.IdProducto
"""

# Comprometido por producto de matrículas cerradas en una ventana.
# Params: ventana_desde, ventana_hasta (YYYY-MM-DD, hasta exclusivo).
SQL_COMPROMETIDO_VENTANA_POR_PRODUCTO = f"""
SELECT op.IdProducto AS P,
  COUNT(DISTINCT op.Id) AS MatricVentana,
  SUM(cp.Total) AS CompVentanaUSD
FROM adm.Oportunidad op
INNER JOIN (
  SELECT he.IdOportunidad, MIN(he.FechaCreacion) AS FMat
  FROM adm.HistorialEstado he
  WHERE {matricula_evento()}
  GROUP BY he.IdOportunidad
) m ON m.IdOportunidad = op.Id AND m.FMat >= ? AND m.FMat < ?
INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = op.Id AND cp.Estado = 1
WHERE op.Estado = 1
GROUP BY op.IdProducto
"""

# ── Variante COHORTE (base = fecha de creación de la oportunidad) ──
# Mismas magnitudes que las de arriba pero ancladas a Oportunidad.FechaCreacion:
# toda la plata pertenece a la cohorte de oportunidades CREADAS en la ventana,
# sin importar cuándo se pagó o se matriculó. Params: creacion_desde, creacion_hasta.

# Cobrado = TODOS los pagos de oportunidades creadas en la ventana (cualquier fecha de pago).
SQL_COBRADO_COHORTE_POR_PRODUCTO = """
SELECT op.IdProducto AS P, SUM(pago.Monto) AS CobradoUSD
FROM adm.CobranzaPago pago
INNER JOIN adm.CobranzaPlan cp   ON cp.Id = pago.IdCobranzaPlan AND cp.Estado = 1
INNER JOIN adm.Oportunidad op    ON op.Id = cp.IdOportunidad AND op.Estado = 1
WHERE pago.Estado = 1 AND op.FechaCreacion >= @desde AND op.FechaCreacion < @hasta
GROUP BY op.IdProducto
"""

# Comprometido = plan total de las oportunidades creadas en la ventana que matricularon
# (estado 3), sin importar cuándo se matricularon. MatricVentana cuenta esa misma cohorte.
SQL_COMPROMETIDO_COHORTE_POR_PRODUCTO = f"""
SELECT op.IdProducto AS P,
  COUNT(DISTINCT op.Id) AS MatricVentana,
  SUM(cp.Total) AS CompVentanaUSD
FROM adm.Oportunidad op
INNER JOIN (
  SELECT he.IdOportunidad
  FROM adm.HistorialEstado he
  WHERE {matricula_evento()}
  GROUP BY he.IdOportunidad
) m ON m.IdOportunidad = op.Id
INNER JOIN adm.CobranzaPlan cp ON cp.IdOportunidad = op.Id AND cp.Estado = 1
WHERE op.Estado = 1 AND op.FechaCreacion >= @desde AND op.FechaCreacion < @hasta
GROUP BY op.IdProducto
"""

# Leads por (producto, asesor) para TODOS los productos — base del FTE por producto.
SQL_LEADS_PRODUCTO_POR_ASESOR_TODOS = """
SELECT op.IdProducto AS P, he.IdPersonal AS A, COUNT(DISTINCT he.IdOportunidad) AS LP
FROM adm.HistorialEstado he
INNER JOIN adm.Oportunidad op ON op.Id = he.IdOportunidad AND op.Estado = 1
WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
GROUP BY op.IdProducto, he.IdPersonal
"""


# ────────────────────────────────────────────────────────────────────────
# Cohort ramp-up: por (asesor, mes desde su ingreso) — leads + matrículas.
# Sólo asesores con FechaIngreso >= ?
# ────────────────────────────────────────────────────────────────────────

# Asesores con FechaIngreso (real o efectiva) >= ?  Devuelve ambas fechas
# para que el caller pueda mostrarlas. Filtro y display dependen de hr_mode.
def sql_asesores_ingreso_desde(hr_mode: bool = False) -> str:
    ingreso = effective_ingreso_expr(hr_mode)
    return f"""
SELECT p.Id,
  LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))) AS Nombre,
  CONVERT(varchar(10), p.FechaIngreso, 23) AS FechaIngresoReal,
  CONVERT(varchar(10), {ingreso}, 23)      AS FechaIngresoEfectiva,
  p.IdTipoJornada AS Jornada
FROM adm.Personal p
WHERE p.Estado = 1 AND ISNULL(p.Cesado, 0) = 0
  AND p.FechaIngreso IS NOT NULL
  AND {ingreso} >= ?
"""


# Leads asignados por (asesor, mes-offset desde FechaIngreso). Param: since.
# Sólo cuenta la primera vez que el asesor tocó cada oportunidad (rn=1) — ver SQL_LEADS_ASIGNADOS.
def sql_cohort_leads(hr_mode: bool = False) -> str:
    ingreso = effective_ingreso_expr(hr_mode)
    return f"""
SELECT q.IdPersonal,
  DATEDIFF(month, {ingreso}, q.FechaCreacion) + 1 AS MesOffset,
  COUNT(*) AS LeadsAsignados
FROM (
  SELECT he.IdPersonal, he.IdOportunidad, he.FechaCreacion,
    ROW_NUMBER() OVER (PARTITION BY he.IdOportunidad, he.IdPersonal ORDER BY he.FechaCreacion, he.Id) AS rn
  FROM adm.HistorialEstado he
  WHERE he.Estado = 1 AND he.IdPersonal IS NOT NULL
) q
INNER JOIN adm.Personal p ON p.Id = q.IdPersonal AND p.Estado = 1
  AND ISNULL(p.Cesado, 0) = 0 AND p.FechaIngreso IS NOT NULL AND {ingreso} >= ?
WHERE q.rn = 1
  AND q.FechaCreacion >= {ingreso}
GROUP BY q.IdPersonal, DATEDIFF(month, {ingreso}, q.FechaCreacion) + 1
"""


# Matrículas por (asesor, mes-offset desde FechaIngreso). Param: since.
def sql_cohort_matriculas(hr_mode: bool = False) -> str:
    ingreso = effective_ingreso_expr(hr_mode)
    return f"""
SELECT he.IdPersonal,
  DATEDIFF(month, {ingreso}, he.FechaCreacion) + 1 AS MesOffset,
  COUNT(DISTINCT he.IdOportunidad) AS Matriculas
FROM adm.HistorialEstado he
INNER JOIN adm.Personal p ON p.Id = he.IdPersonal AND p.Estado = 1
  AND ISNULL(p.Cesado, 0) = 0 AND p.FechaIngreso IS NOT NULL AND {ingreso} >= ?
WHERE {matricula_evento()} AND he.IdPersonal IS NOT NULL
  AND he.FechaCreacion >= {ingreso}
GROUP BY he.IdPersonal, DATEDIFF(month, {ingreso}, he.FechaCreacion) + 1
"""


# ──────────────────────────────────────────────────────────────────────────
# ORIGEN del lead — canal de captación  (conversion_por_origen.py)
#
# Oportunidad.Origen es el CANAL, no la campaña. Valores reales:
#   Linkedin (~99%), Manual, Wordpress, FormularioWeb, NULL.
# El nombre de campaña sólo existe para Linkedin → adm.LinkedIn_Lead.FormName
# (ver sql_linkedin_formnames). No hay FK directa Oportunidad↔LinkedIn_Lead.
#
# Convertido = la oportunidad alcanzó alguna vez estado Matriculado (IdEstado=3).
# OJO: se usa LEFT JOIN a un set DISTINCT de "won" — NO un subquery escalar
# dentro del SUM/aggregate; SQL Server lo rechaza ("Cannot perform an aggregate
# function on an expression containing an aggregate or a subquery"). Ver P18.
# ──────────────────────────────────────────────────────────────────────────

def sql_conversion_por_origen(
    incluir_eliminados: bool = False,
    desde: str | None = None,
    hasta: str | None = None,
) -> tuple[str, list]:
    """Leads y matrículas por Origen. Devuelve (sql, params)."""
    preds: list[str] = []
    params: list = []
    if not incluir_eliminados:
        preds.append("o.Estado = 1")
    if desde:
        preds.append("o.FechaCreacion >= ?")
        params.append(desde)
    if hasta:
        preds.append("o.FechaCreacion < DATEADD(day, 1, CAST(? AS date))")
        params.append(hasta)
    where = ("WHERE " + " AND ".join(preds)) if preds else ""
    sql = f"""
SELECT ISNULL(o.Origen, '(NULL)') AS Origen,
       COUNT(*) AS Leads,
       SUM(CASE WHEN w.IdOportunidad IS NULL THEN 0 ELSE 1 END) AS Matriculas
FROM adm.Oportunidad o
LEFT JOIN (
  SELECT DISTINCT IdOportunidad
  FROM adm.HistorialEstado
  WHERE IdEstado = 3 AND Estado = 1
) w ON w.IdOportunidad = o.Id
{where}
GROUP BY o.Origen
"""
    return sql, params


# ──────────────────────────────────────────────────────────────────────────
# Campañas de LinkedIn — adm.LinkedIn_Lead.FormName  (linkedin_campanas.py)
#
# FormName es el nombre legible de la campaña/formulario (CampaignId es numérico).
# Naming pattern: [FOR-]<FORMATO><TEMA>[NIVEL][SEGMENTO], todo en MAYÚSCULAS sin
# separadores. FORMATO ∈ {PAE, CEP, PEP, PAD} cubre >94% de los leads; el prefijo
# FOR- es la variante "formulario" del mismo código. Hay cola larga ad-hoc
# (WOMANLEAD, "PUENTES DE PAPEL", HABISITE2026…) que no sigue el patrón.
#
# adm.LinkedIn_Lead NO tiene columna Estado (no hay soft-delete aquí). TestLead=1
# marca leads de prueba; excluibles con incluir_test=False.
# ──────────────────────────────────────────────────────────────────────────

def sql_linkedin_formnames(
    buscar: str | None = None,
    incluir_test: bool = True,
) -> tuple[str, list]:
    """Agregado de leads por FormName. Devuelve (sql, params)."""
    preds = ["FormName IS NOT NULL"]
    params: list = []
    if not incluir_test:
        preds.append("ISNULL(TestLead, 0) = 0")
    if buscar:
        preds.append("FormName LIKE ?")
        params.append(f"%{buscar}%")
    where = "WHERE " + " AND ".join(preds)
    sql = f"""
SELECT FormName,
       COUNT(*) AS Leads,
       CONVERT(varchar(10), MIN(CreatedDate), 23) AS Primera,
       CONVERT(varchar(10), MAX(CreatedDate), 23) AS Ultima
FROM adm.LinkedIn_Lead
{where}
GROUP BY FormName
"""
    return sql, params
