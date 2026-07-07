# Guía de migración a PostgreSQL

Olympus migrará de SQL Server a PostgreSQL. La capa de conexión ya es
provider-agnostic (`lib/db_backends/`, seleccionable con `DB_DIALECT`); lo que
queda pendiente es portar el **dialecto SQL** de las queries. Este archivo es
el inventario de construcciones T-SQL en `lib/` y `scripts/` y su equivalente.

## Pasos de infraestructura (una sola vez)

1. Implementar `lib/db_backends/postgres.py` (ver TODOs en el propio archivo):
   `psycopg[binary]`, TLS vía `DB_SSLMODE`/`DB_SSLROOTCERT`, traducción de
   placeholders `?` → `%s` (ya esbozada).
2. `DB_DIALECT=postgres` en `.env` del despliegue nuevo.

## Inventario de T-SQL a portar (conteo al 2026-07-07)

| Construcción T-SQL | Usos | Equivalente PostgreSQL |
|---|---|---|
| `ISNULL(x, y)` | 36 | `COALESCE(x, y)` (ANSI; preferir COALESCE también en SQL nuevo) |
| `DATEADD(day, -n, d)` | 18 | `d - (n * INTERVAL '1 day')` o `d - n` si `d` es `date` |
| `GETDATE()` | 12 | `NOW()` / `CURRENT_DATE` (ojo: GETDATE() es datetime local del server) |
| `DATEDIFF(unit, a, b)` | 10 | días: `b::date - a::date`; minutos: `EXTRACT(EPOCH FROM b-a)/60` |
| `CONVERT(varchar(10), d, 23)` | 9 | `TO_CHAR(d, 'YYYY-MM-DD')` |
| `DATEPART(hour, d)` | 2 | `EXTRACT(HOUR FROM d)` |
| `DECLARE @v = ?` | 1 | No existe en un solo statement; reescribir `SQL_PROGRAMAS_TOP_VENTAS` como CTE con los params una vez, o dejar que el backend repita los params |
| `CAST(x AS date)` | varios | Igual (ANSI) ✓ |
| `ROW_NUMBER() / LAG() OVER (...)` | 9 | Igual (ANSI) ✓ |
| `LIKE` case-insensitive | varios | En SQL Server depende del collation (aquí CI); en Postgres usar `ILIKE` |

## Puntos únicos que concentran el riesgo

- `lib/queries.py::sql_llamadas_delta()` — todo el patrón LAG-delta se porta en UNA función.
- `lib/queries.py::matricula_evento()` — predicado canónico de matrícula, un solo sitio.
- `lib/queries.py::fecha_filter()` y las expresiones `DATEADD(day, -?, CAST(GETDATE() AS date))` — centralizar en un helper por dialecto cuando llegue la migración.
- Semántica de `LIKE`: auditar los filtros de texto (`paises_priority`, `product_search`, `asesores_por_area::AREA_CASE`) por el cambio de collation.

## Regla para SQL nuevo desde hoy

Preferir ANSI: `COALESCE` sobre `ISNULL`, `CAST` sobre `CONVERT`, funciones de
ventana estándar. Cada T-SQLismo nuevo agranda esta tabla.
