# -*- coding: utf-8 -*-
"""Tests del módulo lib/forecast_gp.py (puro, sin BD) — modelo DIARIO."""
from datetime import date, timedelta

import pytest

torch = pytest.importorskip("torch")
gpytorch = pytest.importorskip("gpytorch")

from lib import forecast_gp as fg  # noqa: E402

HOY = date(2026, 7, 6)


def _dias(n, d0=date(2026, 6, 1)):
    return [d0 + timedelta(days=i) for i in range(n)]


# ------------------ deadlines / familia ------------------

def test_parse_deadline_codigo():
    assert fg.parse_deadline("imbpepkeyacc05261") == date(2026, 5, 1)
    assert fg.parse_deadline("imbpaegerprodauto08261") == date(2026, 8, 1)


def test_parse_deadline_sin_patron():
    assert fg.parse_deadline("SINPATRON") is None
    assert fg.parse_deadline(None) is None


def test_parse_deadline_prioriza_fecha_inicio():
    assert fg.parse_deadline("imbpepkeyacc05261", "2026-09-15",
                             hoy=date(2026, 7, 5)) == date(2026, 9, 15)


def test_parse_deadline_fecha_inicio_vieja_cae_al_codigo():
    assert fg.parse_deadline("imbpepkeyacc09261", "2024-01-01",
                             hoy=date(2026, 7, 5)) == date(2026, 9, 1)


def test_parse_familia():
    assert fg.parse_familia("imbpepkeyacc05261") == "PEP"
    assert fg.parse_familia("imbcepausigtriiso08261") == "CEP"
    assert fg.parse_familia("xxx") is None


def test_horizontes():
    assert fg.semanas_restantes(date(2026, 8, 1), date(2026, 7, 5)) == 4
    assert fg.semanas_restantes(date(2026, 6, 1), date(2026, 7, 5)) == 0
    assert fg.dias_restantes(date(2026, 8, 1), date(2026, 7, 5)) == 27
    assert fg.dias_restantes(date(2026, 6, 1), date(2026, 7, 5)) == 0


# ------------------ preparación de series diarias ------------------

def test_prepare_xy_excluye_hoy():
    dias = _dias(6, HOY - timedelta(days=5))  # incluye HOY (incompleto)
    prep = fg.prepare_xy(dias, [100, 110, 105, 120, 115, 40],
                         min_valid=None, hoy=HOY)
    assert prep is not None
    _, y, sc = prep
    assert len(y) == 5  # el día de hoy quedó fuera
    assert sc["y_raw"].tolist() == [100, 110, 105, 120, 115]


def test_prepare_xy_minimo_5_dias():
    dias = _dias(4)
    assert fg.prepare_xy(dias, [50, 60, 40, 55], min_valid=None, hoy=HOY) is None
    dias5 = _dias(5)
    assert fg.prepare_xy(dias5, [50, 60, 40, 55, 45], min_valid=None, hoy=HOY) is not None


def test_prepare_xy_min_valid_filtra_dias_bajos():
    dias = _dias(10)
    counts = [2, 3, 50, 60, 55, 70, 65, 80, 1, 75]
    _, y, sc = fg.prepare_xy(dias, counts, min_valid=15, hoy=HOY)
    assert len(y) == 7  # los días de 2, 3 y 1 leads quedan fuera


# ------------------ GP diario ------------------

def test_gp_prediccion_7dias_razonable_y_cuantiles_ordenados():
    dias = _dias(20)
    leads = [80, 90, 76, 100, 104, 122, 96, 140, 130, 144,
             150, 160, 148, 170, 176, 168, 180, 190, 186, 200]
    X, y, sc = fg.prepare_xy(dias, leads, min_valid=None, hoy=HOY)
    model, _ = fg.init_and_train(X, y, n_iter=300)
    p = fg.predict_one_week_ahead(model, sc, mc_samples=2000)
    assert p["pessimistic"] <= p["mean"] <= p["optimistic"]
    assert p["lower"] <= p["p80"] <= p["p90"] <= p["p95"] <= p["upper"] * 1.001
    # 7 días a ~180-220/día → suma plausible en [700, 3500]
    assert 700 < p["mean"] < 3500
    assert p["var_latent"] > 0


def test_project_cumulative_dias():
    dias = _dias(12)
    ventas = [1, 2, 1, 4, 3, 5, 4, 6, 5, 7, 6, 8]
    X, y, sc = fg.prepare_xy(dias, ventas, min_valid=None, hoy=HOY)
    model, _ = fg.init_and_train(X, y, n_iter=300)
    proj = fg.project_cumulative(model, sc, 14, mc_samples=2000)
    assert proj["p05"] <= proj["p50"] <= proj["p95"]
    assert proj["mean"] > 0
    zero = fg.project_cumulative(model, sc, 0, mc_samples=100)
    assert zero["mean"] == 0.0


def test_mc_total_scenario():
    lat = {"A": (5.0, 0.04), "B": (4.5, 0.09)}
    mc = fg.mc_total_and_scenario(lat, target_total=250, mc_samples=4000)
    assert mc["total"]["min"] <= mc["total"]["p50"] <= mc["total"]["max"]
    pp = mc["per_program"]["A"]
    assert pp["cond_p10"] <= pp["cond_p50"] <= pp["cond_p90"]
    assert mc["scenario_total_int"] >= 0


# ------------------ fallback Wilson ------------------

def test_fallback_wilson_producto_propio():
    r = fg.project_fallback_wilson(ventas=5, leads=200, leads_sem_mediana=100,
                                   semanas_restantes=4)
    assert r["metodo"] == "WILSON"
    assert r["p05"] <= r["mean"] <= r["p95"]
    assert r["mean"] == pytest.approx(5 + (5 / 200) * 400)


def test_fallback_wilson_familia():
    r = fg.project_fallback_wilson(ventas=0, leads=10, leads_sem_mediana=50,
                                   semanas_restantes=4, tc_familia=(30, 3000))
    assert r["tc_mid"] == pytest.approx(0.01)


# ------------------ break-even ------------------

def _params():
    return fg.BreakevenParams()  # 3.78, 11%, 10%, 565/1130


def test_breakeven_caso_manual():
    # 668×3.78×0.79 = 1994.83; margen = 1994.83 − 275 − 5/0.03 = 1553.16 → N_BE = 4
    be = fg.compute_breakeven(668, 0.03, 5.0, 5443.2, 275.0, _params())
    assert be.n_be == 4
    assert be.ticket_neto_pen == pytest.approx(668 * 3.78 * 0.79)


def test_breakeven_margen_negativo_inviable():
    be = fg.compute_breakeven(100, 0.005, 8.0, 5443.2, 275.0, _params())
    assert be.n_be is None
    assert fg.decidir(be.n_be, 10, 20) == "CANCELAR"


def test_decisiones():
    assert fg.decidir(10, 12, 15) == "CONTINUAR"
    assert fg.decidir(10, 8, 15) == "RIESGO"
    assert fg.decidir(10, 5, 8) == "CANCELAR"
    assert fg.decidir(10, 5, 8, sin_deadline=True) == "SIN_DEADLINE"


def test_cac():
    assert fg.cac_por_jornada(565, 1200, 300) == pytest.approx(141.25)
    assert fg.cac_blend(280, 260, ventas_ft=1, ventas_pt=3) == pytest.approx(265.0)
    assert fg.cac_blend(280, 260, 0, 0) == pytest.approx(270.0)


def test_leads_semanales_necesarios():
    assert fg.leads_semanales_necesarios(10, 4, 0.03, 4) == 50
    assert fg.leads_semanales_necesarios(None, 4, 0.03, 4) is None
    assert fg.leads_semanales_necesarios(10, 12, 0.03, 4) == 0
