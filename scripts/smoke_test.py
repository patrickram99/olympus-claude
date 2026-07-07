#!/usr/bin/env python3
"""
Smoke test — verifica que el paquete carga sin errores y los cálculos puros funcionan.

NO conecta a la base de datos. Útil para confirmar que el setup local (pyodbc,
python-dotenv, tabulate) está instalado y que `lib/calc.py` produce los números
esperados ANTES de configurar credenciales en `.env`.

Uso:
  python scripts/smoke_test.py

Sale con código 0 si todo OK, 1 si algún check falló.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    failures: list[str] = []

    # ─── 1. Importar todos los módulos de la librería ─────────────────────
    try:
        from lib import calc, db, format as fmt, queries  # noqa: F401
        print("[OK] lib.{calc,db,queries,format} importados")
    except Exception as e:
        print(f"[FAIL] no se pueden importar módulos de lib: {e}")
        return 1

    # ─── 2. Worked example: producto imbpepkeyacc05261 (calculations.md §6) ─
    from lib.calc import CostParams, ProductBaseline, compute_pnl, fte_equivalents, wilson_lb

    baseline = ProductBaseline(
        leads=3715,
        matriculados=12,
        fte=3.29,
        monto_comprometido_usd=6364.53,
        monto_cobrado_usd=4226.86,
        costo_base_usd=550,
    )
    params = CostParams()  # defaults: 565/0.20/10%/10%/1440/3.78
    pnl = compute_pnl(baseline, params, ingreso_mode="cobrado")

    if abs(pnl.margen_pen - 2669.0) > 5.0:
        failures.append(f"margen_pen={pnl.margen_pen:.2f}, esperado ~+2669 ±5")
    else:
        print(f"[OK] compute_pnl margen = {pnl.margen_pen:.2f} PEN (esperado ~+2669)")

    if abs(pnl.costo_total - 13308.51) > 3.0:
        failures.append(f"costo_total={pnl.costo_total:.2f}, esperado ~13308.51 ±3")
    else:
        print(f"[OK] compute_pnl costo_total = {pnl.costo_total:.2f} PEN (esperado ~13308.51)")

    if abs(pnl.costo_por_matricula - 1109.0) > 1.0:
        failures.append(f"costo_por_matricula={pnl.costo_por_matricula:.2f}, esperado ~1109 ±1")
    else:
        print(f"[OK] compute_pnl costo/matrícula = {pnl.costo_por_matricula:.2f} PEN (esperado ~1109)")

    # ─── 3. Sanity checks Wilson + FTE ────────────────────────────────────
    if wilson_lb(0, 0) != 0.0:
        failures.append("wilson_lb(0, 0) debería ser 0")
    if wilson_lb(50, 1000) <= wilson_lb(1, 10):
        failures.append("Wilson LB con muestra grande debería superar a (1,10)")
    if abs(fte_equivalents({1: 10, 2: 20}, {1: 100, 2: 100}) - 0.3) > 1e-9:
        failures.append("fte_equivalents({1:10, 2:20}, {1:100, 2:100}) debería ser 0.3")
    if not failures:
        print("[OK] sanity Wilson + FTE")

    # ─── 4. Reportar ─────────────────────────────────────────────────────
    if failures:
        print("\n>>> FAIL: " + str(len(failures)) + " problemas:")
        for f in failures:
            print(f"   - {f}")
        return 1

    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
