# Olympus CRM Analytics — Skill + Scripts

Skill de Claude + librería ejecutable de Python para analizar el CRM Olympus (IMB / IESL Institute) sobre SQL Server.

## Estructura

```
olympus-crm-analytics/
├── SKILL.md                  # entry point para Claude
├── README.md                 # este archivo
├── .env.example              # template de credenciales
├── requirements.txt          # pyodbc, python-dotenv, tabulate
├── lib/
│   ├── db.py                 # capa de conexión provider-agnostic (singleton)
│   ├── db_backends/          # backends por proveedor: mssql (actual), postgres (stub); TLS/certs viven aquí
│   ├── calc.py               # Wilson LB, FTE attribution, sensibilidad
│   ├── cli.py                # argparse compartido: --top acotado, iso_date, --desde con alias
│   ├── queries.py            # SQL templates parametrizados (índice de secciones en el docstring)
│   ├── forecast_gp.py        # forecast con Gaussian Processes (módulo puro)
│   └── format.py             # output table/csv/json
├── scripts/                  # ejecutables CLI
│   ├── pipeline_kpis.py
│   ├── asesores_top.py
│   ├── asesor_detail.py
│   ├── producto_pnl.py
│   ├── paises_priority.py
│   ├── time_to_first_sale.py
│   ├── calls_by_hour.py
│   ├── funnel_transitions.py
│   └── product_search.py
├── docs/                     # historial (rollouts, decisiones)
└── references/               # docs para Claude (no para ejecutar)
    ├── schema.md
    ├── queries.md
    ├── calculations.md
    ├── pitfalls.md
    └── postgres_migration.md # inventario T-SQL→Postgres para la migración
```

## Setup

```bash
# Instalar deps (sin venv, root install)
pip install -r requirements.txt

# Configurar .env
cp .env.example .env
# editar con DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME

# Validar
python scripts/pipeline_kpis.py --periodo 7
```

Si la validación imprime KPIs en tabla, todo OK. Si hay error de conexión, revisa `.env` o instala "ODBC Driver 18 for SQL Server" desde Microsoft.

## Seguridad y proveedor de BD

- El proveedor se elige con `DB_DIALECT` en `.env` (hoy `mssql`; `postgres` quedará habilitado con la migración). Lo específico de cada proveedor — driver, connection string, TLS/certificados — vive en `lib/db_backends/`, así el cambio de proveedor o de certificado no toca scripts ni queries.
- `.env` nunca se versiona ni se empaqueta (está en `.gitignore`).
- **Pendiente (D1) para el despliegue como MCP server de empresa:** crear una credencial de servicio **read-only** dedicada en la BD y usarla en lugar de credenciales personales.

## Uso desde CLI

Cada script tiene `--help`:
```bash
python scripts/asesores_top.py --help
```

### Ejemplos comunes

```bash
# Snapshot global del último mes
python scripts/pipeline_kpis.py --periodo 30

# Top 10 asesores con muestra ≥ 30 leads
python scripts/asesores_top.py --top 10 --umbral 30

# Detalle del asesor 81 (período 90 días)
python scripts/asesor_detail.py 81

# P&L de un producto con defaults
python scripts/producto_pnl.py 381

# What-if: ¿qué pasa si subo el CPL a 0.30 USD?
python scripts/producto_pnl.py 381 --cpl 0.30

# Países para cursos de mantenimiento y finanzas
python scripts/paises_priority.py --tema "mantenimiento|finanzas"

# Time-to-first-sale asesores ingresados en 2026
python scripts/time_to_first_sale.py --since 2026-01-01 -o asesores_ttfs.csv

# Mejor hora para llamar
python scripts/calls_by_hour.py

# Buscar productos por código
python scripts/product_search.py "imbpepkeyacc"

# Funnel del asesor 81
python scripts/funnel_transitions.py --asesor 81
```

## Uso desde Claude (con la skill activada)

Cuando preguntes algo en lenguaje natural, Claude:
1. Detectará que es una pregunta sobre Olympus.
2. Identificará el script apropiado vía el mapping en `SKILL.md`.
3. Ejecutará el script con los parámetros correctos.
4. Te devolverá los resultados formateados, con caveats.

Si no hay script para tu pregunta, Claude cae a `mcp__mssql__execute_sql` usando los templates en `references/queries.md`.

## Convenciones

- **Output**: por defecto tabla bonita en stdout. Para guardar: `--fmt csv -o archivo.csv`.
- **Moneda**: USD donde la DB lo tiene, PEN en cálculos de costo. Default USD→PEN = 3.78 (configurable en `.env`).
- **Período**: días hacia atrás (`--periodo 30`).
- **Umbral**: leads mínimos para considerar en rankings (anti-outlier, default 30).

## Testing rápido del setup

```bash
python scripts/product_search.py "Key Account"
# debería listar productos con "Key Account" en el nombre

python scripts/pipeline_kpis.py --periodo 7
# debería imprimir KPIs reales del último mes

python scripts/producto_pnl.py 381
# si el producto 381 existe, debería dar P&L completo con margen
```

## Troubleshooting

- **`ModuleNotFoundError: pyodbc`** → `pip install pyodbc`
- **`Can't open lib 'ODBC Driver 18 for SQL Server'`** → instalar el driver de Microsoft.
- **`Login failed`** → revisar credenciales en `.env`.
- **Timeout en queries grandes** → el script ya divide en sub-queries; si persiste, baja `--periodo`.

## Extender con scripts nuevos

1. Agrega query template a `lib/queries.py`.
2. Crea `scripts/nuevo_script.py` siguiendo el patrón:
   - argparse
   - `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`
   - importa `lib.db`, `lib.queries`, `lib.calc`, `lib.format`
   - `output(rows, fmt=args.fmt, out_path=args.output)` al final
3. Documenta en `SKILL.md` (sección "Available scripts" + tabla "Mapeo de pregunta → script").
