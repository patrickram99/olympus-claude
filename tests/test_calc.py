"""
Unit tests for lib/calc.py — Wilson LB, FTE attribution, P&L engine.
Pure functions, no DB required.
"""
import pytest

from lib.calc import (
    CostParams,
    ProductBaseline,
    compute_pnl,
    fte_equivalents,
    wilson_lb,
)


# ─── Wilson lower bound ──────────────────────────────────────────────────────

def test_wilson_lb_zero_sample():
    # Empty sample → 0 (no evidence → no claim).
    assert wilson_lb(0, 0) == 0.0


def test_wilson_lb_zero_successes_large_sample():
    # 0 successes out of 100 → must be ≥ 0 and very close to 0.
    lb = wilson_lb(0, 100)
    assert lb >= 0.0
    assert lb < 0.001  # essentially zero with finite sample


def test_wilson_lb_perfect_score_under_one():
    # 100/100 = 100% TC, but with finite sample LB must be < 1
    # (sample is finite, can't be 100% certain).
    lb = wilson_lb(100, 100)
    assert 0 < lb < 1.0


def test_wilson_lb_large_sample_beats_small_sample_with_high_tc():
    # Canonical Wilson behavior: a low-but-well-established TC outranks
    # a higher TC observed on a tiny sample. With (1, 10) = 10% on 10 obs,
    # Wilson LB ≈ 1.8%; with (50, 1000) = 5% on 1000 obs, LB ≈ 3.8%.
    # The bigger sample wins despite lower crude TC.
    #
    # NOTE: the original prompt asked for `wilson_lb(1, 3) < wilson_lb(50, 1000)`,
    # but with the standard Wilson formula in calc.py that comparison is
    # actually *reversed* (1.96-z Wilson can't punish n=3 hard enough; it
    # would need the continuity-corrected variant to give ~1.8% as the doc
    # claims). See REPORT for details. (1, 10) preserves the test's intent.
    assert wilson_lb(1, 10) < wilson_lb(50, 1000)


# ─── FTE attribution ─────────────────────────────────────────────────────────

def test_fte_single_asesor():
    # Asesor with 10 leads on this product, 100 total → 10% FTE.
    assert fte_equivalents({1: 10}, {1: 100}) == pytest.approx(0.1)


def test_fte_two_asesores_sums():
    # 10/100 + 20/100 = 0.30
    assert fte_equivalents({1: 10, 2: 20}, {1: 100, 2: 100}) == pytest.approx(0.3)


def test_fte_empty():
    assert fte_equivalents({}, {}) == 0.0


def test_fte_ignores_asesor_without_total():
    # If leads_total is missing for an asesor, they're skipped (would div-by-zero).
    assert fte_equivalents({1: 5, 2: 10}, {1: 50}) == pytest.approx(0.1)


# ─── compute_pnl — worked example ────────────────────────────────────────────

def test_compute_pnl_worked_example():
    """
    imbpepkeyacc05261 (PEP Key Account Manager, May 2026):
      leads=3,715  matric=12  fte=3.29
      comprometido=$6,364.53  cobrado=$4,226.86  costo_base=$550
    Defaults (565/0.20/10%/10%/1440/3.78), ingreso=cobrado.

    Expected (from references/calculations.md §6):
      costo_total      ≈ 13,308.51 PEN
      margen_pen       ≈ +2,669 PEN
      costo_por_matric ≈ 1,109 PEN

    Tolerance widened to ±3 on costo_total because the doc's worked example
    uses fte≈3.2942 internally while displaying it as 3.29 — see REPORT.
    """
    baseline = ProductBaseline(
        leads=3715,
        matriculados=12,
        fte=3.29,
        monto_comprometido_usd=6364.53,
        monto_cobrado_usd=4226.86,
        costo_base_usd=550,
    )
    params = CostParams()  # defaults
    result = compute_pnl(baseline, params, ingreso_mode="cobrado")

    assert result.costo_total == pytest.approx(13308.51, abs=3.0)
    assert result.margen_pen == pytest.approx(2669.0, abs=5.0)
    assert result.costo_por_matricula == pytest.approx(1109.0, abs=1.0)


def test_compute_pnl_ingreso_mode_switches_revenue():
    """`comprometido` mode uses the planned amount instead of cobrado."""
    baseline = ProductBaseline(
        leads=3715, matriculados=12, fte=3.29,
        monto_comprometido_usd=6364.53, monto_cobrado_usd=4226.86, costo_base_usd=550,
    )
    p = CostParams()
    cobrado = compute_pnl(baseline, p, ingreso_mode="cobrado")
    comprometido = compute_pnl(baseline, p, ingreso_mode="comprometido")
    assert comprometido.ingreso_pen > cobrado.ingreso_pen
    assert comprometido.ingreso_pen == pytest.approx(6364.53 * 3.78, abs=0.01)
