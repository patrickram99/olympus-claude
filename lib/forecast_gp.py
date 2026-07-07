# -*- coding: utf-8 -*-
"""
Forecast de leads/ventas con Gaussian Processes (GPyTorch) + break-even.

Módulo PURO: sin IO ni BD — recibe series y parámetros, devuelve proyecciones
y decisiones. Es la implementación canónica; el notebook de Colab
(Work\\Forecast\\notebooks\\forecast_colab.ipynb) lleva una copia literal de
estas funciones — cualquier fix se aplica en ambos lados.

Arquitectura del GP (código de referencia del usuario, adaptado a GRANO DIARIO —
los leads y las ventas entran en tiempo real, así que el GP se ajusta sobre la
serie DIARIA y con >=5 días de datos ya corre):
  - y = log1p(conteo DIARIO); x = días desde el primer punto, normalizados a [0,1]
  - ExactGP: ZeroMean + ScaleKernel(RBF) con priors LogNormal y clamps
  - FixedNoiseGaussianLikelihood con ruido por programa = MAD de las diferencias log
  - Predicciones por horizonte (p.ej. "próxima semana") = suma Monte Carlo de los
    próximos N días muestreados conjuntamente del posterior → media + cuantiles
    optimista/pesimista (P80/P90/P95)
  - Monte Carlo para distribución de totales y escenario alineado a un target
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import torch
import gpytorch

# ------------------ Config (defaults del código de referencia) ------------------
MC_SAMPLES = 20000
RNG_SEED = 42
TARGET_TOL_FRAC = 0.02
TARGET_TOL_MIN = 50
OPTIMISM_Q = 0.95
LOOKBACK_DIAS = None       # usar solo los últimos N días (None = todos)
MIN_VALID_LEADS_DIA = 15   # ignora días con menos leads (solo GP de leads; None para ventas)
MIN_PUNTOS_GP = 5          # mínimo de días con datos para ajustar el GP
HORIZONTE_PEDIDO_DIAS = 7  # el pedido/predicción "próxima semana" = suma de 7 días
DEFAULT_NOISE_LOG = 0.18
NOISE_LOG_MIN, NOISE_LOG_MAX = 0.12, 0.25
LS_MIN, LS_MAX = 0.25, 2.0
OS_MIN, OS_MAX = 0.05, 2.0
TRAIN_ITERS = 900
TRAIN_LR = 0.03

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DTYPE = torch.float64
torch.set_default_dtype(DTYPE)


# ------------------ Modelo ------------------
class ExactGPModel(gpytorch.models.ExactGP):
    def __init__(self, train_x, train_y, likelihood):
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = gpytorch.means.ZeroMean()
        base_kernel = gpytorch.kernels.RBFKernel(
            lengthscale_prior=gpytorch.priors.LogNormalPrior(math.log(0.45), 0.25)
        )
        base_kernel.lengthscale = 0.45
        self.covar_module = gpytorch.kernels.ScaleKernel(
            base_kernel,
            outputscale_prior=gpytorch.priors.LogNormalPrior(math.log(0.6), 0.35),
        )

    def forward(self, x):
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


# ------------------ Preparación de series (DIARIAS) ------------------
def prepare_xy(day_dates: list[date], counts: list[float],
               lookback_dias: int | None = LOOKBACK_DIAS,
               min_valid: int | None = MIN_VALID_LEADS_DIA,
               min_puntos: int = MIN_PUNTOS_GP,
               hoy: date | None = None):
    """
    day_dates: fecha de cada DÍA observado; counts: conteo diario.
    Excluye el día de hoy (incompleto: los datos entran en tiempo real).
    Devuelve (X, y, scalers) o None si tras filtrar quedan < min_puntos días.
    """
    hoy = hoy or date.today()
    pairs = sorted((d, c) for d, c in zip(day_dates, counts) if d < hoy)
    if lookback_dias is not None and pairs:
        cutoff = pairs[-1][0] - timedelta(days=lookback_dias)
        filtered = [(d, c) for d, c in pairs if d >= cutoff]
        if len(filtered) >= min_puntos:
            pairs = filtered
    if min_valid is not None:
        pairs = [(d, c) for d, c in pairs if c >= min_valid]
    if len(pairs) < min_puntos:
        return None

    d0 = pairs[0][0]
    x_dias = np.array([(d - d0).days for d, _ in pairs], dtype=float)
    x_max = x_dias.max() if x_dias.max() > 0 else 1.0
    y_raw = np.array([c for _, c in pairs], dtype=float)
    y_log = np.log1p(y_raw)

    X = torch.tensor(x_dias / x_max, dtype=DTYPE, device=DEVICE)
    y = torch.tensor(y_log, dtype=DTYPE, device=DEVICE)
    scalers = dict(x_dias=x_dias, x_max=x_max, first_date=d0, y_raw=y_raw)
    return X, y, scalers


def estimate_noise_log(y: torch.Tensor) -> float:
    """Ruido fijo por programa: MAD de las diferencias log, clampado."""
    y_np = y.detach().cpu().numpy()
    diffs = np.diff(y_np) if len(y_np) > 1 else np.array([DEFAULT_NOISE_LOG])
    noise_est = np.median(np.abs(diffs)) / 0.6745 if diffs.size else DEFAULT_NOISE_LOG
    return float(np.clip(noise_est, NOISE_LOG_MIN, NOISE_LOG_MAX))


def init_and_train(X, y, noise_log: float | None = None,
                   n_iter: int = TRAIN_ITERS, lr: float = TRAIN_LR):
    if noise_log is None:
        noise_log = estimate_noise_log(y)
    noise_vec = torch.full_like(y, noise_log ** 2)
    likelihood = gpytorch.likelihoods.FixedNoiseGaussianLikelihood(
        noise=noise_vec, learn_additional_noise=False
    ).to(DEVICE)

    model = ExactGPModel(X, y, likelihood).to(DEVICE)
    with torch.no_grad():
        model.covar_module.outputscale = 0.6
        model.covar_module.base_kernel.lengthscale = 0.45

    model.train(); likelihood.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    mll = gpytorch.mlls.ExactMarginalLogLikelihood(likelihood, model)

    for _ in range(n_iter):
        optimizer.zero_grad()
        output = model(X)
        loss = -mll(output, y)
        loss.backward()
        optimizer.step()
        with torch.no_grad():
            ls = model.covar_module.base_kernel.lengthscale
            os_ = model.covar_module.outputscale
            model.covar_module.base_kernel.lengthscale = ls.clamp(LS_MIN, LS_MAX)
            model.covar_module.outputscale = os_.clamp(OS_MIN, OS_MAX)

    model.eval(); likelihood.eval()
    return model, likelihood


# ------------------ Back-transform ------------------
def normal_icdf(q: float) -> float:
    return torch.distributions.Normal(0, 1).icdf(torch.tensor(float(q))).item()


def backtransform_stats(mu: float, var: float, qs=(0.8, 0.9, 0.95), alpha: float = 0.05):
    sigma = math.sqrt(max(var, 1e-12))
    mean_raw = math.exp(mu + 0.5 * var) - 1.0
    z = 1.96 if abs(alpha - 0.05) < 1e-9 else normal_icdf(1 - alpha / 2)
    lo_raw = max(0.0, math.exp(mu - z * sigma) - 1.0)
    up_raw = max(0.0, math.exp(mu + z * sigma) - 1.0)
    quantiles = {}
    for q in qs:
        zq = normal_icdf(q)
        quantiles[f"p{int(q * 100)}"] = max(0.0, math.exp(mu + zq * sigma) - 1.0)
    return float(mean_raw), float(lo_raw), float(up_raw), quantiles


def _sum_samples_dias(model, scalers, n_dias: int,
                      mc_samples: int = MC_SAMPLES, seed: int = RNG_SEED) -> np.ndarray:
    """Muestras MC de la suma de los próximos n_dias días (posterior conjunto)."""
    last_dia = scalers["x_dias"].max()
    x_max = scalers["x_max"] if scalers["x_max"] > 0 else 1.0
    xs = torch.tensor([(last_dia + i) / x_max for i in range(1, n_dias + 1)],
                      dtype=DTYPE, device=DEVICE)
    torch.manual_seed(seed)
    with torch.no_grad(), gpytorch.settings.fast_pred_var():
        post = model(xs)
        latent = post.rsample(torch.Size([mc_samples]))       # (mc, n_dias)
    daily = torch.clamp(torch.expm1(latent), min=0.0)
    return daily.sum(dim=1).cpu().numpy()


def predict_one_week_ahead(model, scalers, alpha: float = 0.05,
                           optimism_q: float = OPTIMISM_Q,
                           dias: int = HORIZONTE_PEDIDO_DIAS,
                           mc_samples: int = MC_SAMPLES, seed: int = RNG_SEED) -> dict:
    """
    Predicción del TOTAL de los próximos `dias` días (default 7 = "próxima semana"):
    suma MC de los días muestreados conjuntamente del posterior diario.
    mu_latent/var_latent = ajuste lognormal de las sumas (para el MC de totales).
    """
    sums = _sum_samples_dias(model, scalers, dias, mc_samples, seed)
    log_sums = np.log1p(sums)
    mu, var = float(log_sums.mean()), float(log_sums.var())

    def q(p):
        return float(np.percentile(sums, p))

    return dict(
        mean=float(sums.mean()),
        lower=q(100 * alpha / 2), upper=q(100 * (1 - alpha / 2)),
        optimistic=q(100 * optimism_q), pessimistic=q(100 * (1 - optimism_q)),
        p80=q(80), p90=q(90), p95=q(95),
        mu_latent=mu, var_latent=var,
    )


def project_cumulative(model, scalers, n_dias: int,
                       mc_samples: int = MC_SAMPLES, seed: int = RNG_SEED) -> dict:
    """
    Distribución MC de la suma de conteos de los próximos n_dias DÍAS.
    Para el GP de ventas: ventas ADICIONALES esperadas hasta el deadline.
    """
    if n_dias <= 0:
        z = np.zeros(mc_samples)
        return dict(samples=z, mean=0.0, p05=0.0, p50=0.0, p95=0.0)
    totals = _sum_samples_dias(model, scalers, n_dias, mc_samples, seed)
    return dict(
        samples=totals,
        mean=float(totals.mean()),
        p05=float(np.percentile(totals, 5)),
        p50=float(np.percentile(totals, 50)),
        p95=float(np.percentile(totals, 95)),
    )


# ------------------ Monte Carlo de totales + escenario alineado a target ------------------
def mc_total_and_scenario(latents: dict[str, tuple[float, float]], target_total: float,
                          mc_samples: int = MC_SAMPLES, seed: int = RNG_SEED,
                          tol_frac: float = TARGET_TOL_FRAC, tol_min: float = TARGET_TOL_MIN) -> dict:
    """
    latents: {codigo: (mu_latent, var_latent)} de la predicción a 1 semana del GP de leads.
    Devuelve distribución del total, escenario del draw más cercano al target y
    rangos condicionales p10/p50/p90 por programa dado total≈target.
    """
    codes = list(latents.keys())
    mu_vec = np.array([latents[c][0] for c in codes])
    sigma_vec = np.sqrt(np.maximum(np.array([latents[c][1] for c in codes]), 1e-12))

    rng = np.random.default_rng(seed)
    latent_samples = rng.normal(loc=mu_vec[:, None], scale=sigma_vec[:, None],
                                size=(len(codes), mc_samples))
    y_samples = np.maximum(np.exp(latent_samples) - 1.0, 0.0)
    total_samples = y_samples.sum(axis=0)

    tot = dict(
        min=float(total_samples.min()),
        p10=float(np.percentile(total_samples, 10)),
        p50=float(np.percentile(total_samples, 50)),
        p90=float(np.percentile(total_samples, 90)),
        max=float(total_samples.max()),
    )
    inside_range = tot["min"] <= target_total <= tot["max"]
    inside_p10_p90 = tot["p10"] <= target_total <= tot["p90"]

    idx = int(np.argmin(np.abs(total_samples - target_total)))
    rec_cont = y_samples[:, idx]
    rec_total = float(total_samples[idx])
    rec_int = np.maximum(np.rint(rec_cont).astype(int), 0)

    center = float(np.clip(target_total, tot["min"], tot["max"]))
    tol = max(tol_min, tol_frac * max(center, 1.0))
    mask = np.abs(total_samples - center) <= tol
    if not np.any(mask):
        nearest = np.argsort(np.abs(total_samples - center))[: min(200, mc_samples)]
        mask = np.zeros(mc_samples, dtype=bool)
        mask[nearest] = True
    y_cond = y_samples[:, mask]

    per_program = {}
    for i, c in enumerate(codes):
        per_program[c] = dict(
            rec_cont=float(rec_cont[i]),
            rec_int=int(rec_int[i]),
            rec_share=float(rec_cont[i] / rec_total) if rec_total > 0 else 0.0,
            cond_p10=float(np.percentile(y_cond[i], 10)),
            cond_p50=float(np.percentile(y_cond[i], 50)),
            cond_p90=float(np.percentile(y_cond[i], 90)),
        )
    return dict(total=tot, inside_range=inside_range, inside_p10_p90=inside_p10_p90,
                scenario_total=rec_total, scenario_total_int=int(rec_int.sum()),
                per_program=per_program)


# ------------------ Fallback Wilson (series con <3 puntos de venta) ------------------
def wilson_lb(success: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = min(1.0, max(0.0, success / n))
    denom = 1 + (z * z) / n
    center = p + (z * z) / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))
    return max(0.0, (center - margin) / denom)


def wilson_ub(success: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 1.0
    p = min(1.0, max(0.0, success / n))
    denom = 1 + (z * z) / n
    center = p + (z * z) / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))
    return min(1.0, (center + margin) / denom)


def project_fallback_wilson(ventas: int, leads: int, leads_sem_mediana: float,
                            semanas_restantes: int,
                            tc_familia: tuple[int, int] | None = None) -> dict:
    """
    Proyección determinística con incertidumbre binomial cuando el GP de ventas
    no tiene puntos suficientes. tc_familia: (ventas, leads) agregados de la
    familia CEP/PEP/PAE/PAD si el producto no tiene muestra propia (≥30 leads).
    """
    if leads >= 30 and ventas > 0:
        lb, ub = wilson_lb(ventas, leads), wilson_ub(ventas, leads)
        tc_mid = ventas / leads
    elif tc_familia is not None and tc_familia[1] > 0:
        fv, fl = tc_familia
        lb, ub = wilson_lb(fv, fl), wilson_ub(fv, fl)
        tc_mid = fv / fl
    else:
        lb, ub, tc_mid = 0.0, 1.0, 0.0
    extra = leads_sem_mediana * max(0, semanas_restantes)
    return dict(
        mean=ventas + tc_mid * extra,
        p05=ventas + lb * extra,
        p95=ventas + ub * extra,
        tc_lb=lb, tc_ub=ub, tc_mid=tc_mid,
        metodo="WILSON",
    )


# ------------------ Deadlines / familia ------------------
def parse_deadline(codigo: str | None, fecha_inicio: date | None = None,
                   hoy: date | None = None) -> date | None:
    """
    Deadline = FechaInicio si existe y es plausible; si no, parseo del
    CodigoLanzamiento: sufijo MMYY + dígito de release (imbpepkeyacc05261 → 2026-05-01).
    """
    hoy = hoy or date.today()
    if fecha_inicio is not None:
        if isinstance(fecha_inicio, str):
            try:
                fecha_inicio = date.fromisoformat(fecha_inicio[:10])
            except ValueError:
                fecha_inicio = None
        if fecha_inicio is not None and fecha_inicio >= hoy - timedelta(weeks=8):
            return fecha_inicio
    if codigo:
        m = re.search(r"(\d{2})(\d{2})\d$", codigo.strip())
        if m:
            mm, yy = int(m.group(1)), int(m.group(2))
            if 1 <= mm <= 12:
                return date(2000 + yy, mm, 1)
    return None


def parse_familia(codigo: str | None) -> str | None:
    if not codigo:
        return None
    m = re.search(r"(cep|pep|pae|pad)", codigo.lower())
    return m.group(1).upper() if m else None


def semanas_restantes(deadline: date, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return max(0, math.ceil((deadline - hoy).days / 7))


def dias_restantes(deadline: date, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return max(0, (deadline - hoy).days)


# ------------------ Break-even ------------------
@dataclass
class BreakevenParams:
    usd_pen: float = 3.78
    comision_pct: float = 0.11
    admin_pct: float = 0.10
    sueldo_pt_pen: float = 565.0
    sueldo_ft_pen: float = 1130.0


@dataclass
class BreakevenResult:
    ticket_neto_pen: float
    cac_asesor_pen: float
    cpl_por_venta_pen: float
    margen_por_venta_pen: float
    n_be: int | None            # None = margen ≤ 0 (estructuralmente inviable)
    detalle: dict = field(default_factory=dict)


def cac_por_jornada(sueldo_pen: float, llamadas_mes: float, llamadas_por_venta: float) -> float:
    """CAC de asesor = sueldo × (llamadas_por_venta / llamadas_mensuales_promedio)."""
    if llamadas_mes <= 0:
        return 0.0
    return sueldo_pen * (llamadas_por_venta / llamadas_mes)


def cac_blend(cac_ft: float, cac_pt: float, ventas_ft: int, ventas_pt: int) -> float:
    total = ventas_ft + ventas_pt
    if total <= 0:
        return (cac_ft + cac_pt) / 2.0
    return (ventas_ft * cac_ft + ventas_pt * cac_pt) / total


def compute_breakeven(ticket_usd: float, tc: float, cpl_pen: float, docente_pen: float,
                      cac_asesor_pen: float, p: BreakevenParams) -> BreakevenResult:
    """
    Bruto − comisiones(11%) − admin(10%) = ticket neto; luego por venta se
    descuentan CAC de asesor y CPL/TC. El docente es el único costo fijo:
      N_BE = ceil(docente / margen_por_venta)
    """
    ticket_neto = ticket_usd * p.usd_pen * (1.0 - p.comision_pct - p.admin_pct)
    cpl_por_venta = (cpl_pen / tc) if tc > 0 else float("inf")
    margen = ticket_neto - cac_asesor_pen - cpl_por_venta
    n_be = math.ceil(docente_pen / margen) if margen > 0 else None
    return BreakevenResult(
        ticket_neto_pen=ticket_neto,
        cac_asesor_pen=cac_asesor_pen,
        cpl_por_venta_pen=cpl_por_venta,
        margen_por_venta_pen=margen,
        n_be=n_be,
        detalle=dict(ticket_usd=ticket_usd, tc=tc, cpl_pen=cpl_pen, docente_pen=docente_pen),
    )


def decidir(n_be: int | None, proy_media: float, proy_optimista: float,
            sin_deadline: bool = False) -> str:
    """
    CANCELAR  si margen ≤ 0 (n_be None) o ni el escenario optimista llega a N_BE.
    RIESGO    si solo el optimista llega. CONTINUAR si la media llega.
    """
    if n_be is None:
        return "CANCELAR"
    if sin_deadline:
        return "SIN_DEADLINE"
    if proy_optimista < n_be:
        return "CANCELAR"
    if proy_media < n_be:
        return "RIESGO"
    return "CONTINUAR"


def leads_semanales_necesarios(n_be: int | None, ventas_actuales: int, tc: float,
                               semanas_rest: int) -> int | None:
    """Leads/semana a solicitar para cubrir las ventas faltantes hasta el deadline."""
    if n_be is None or tc <= 0 or semanas_rest <= 0:
        return None
    faltan = max(0, n_be - ventas_actuales)
    return math.ceil((faltan / tc) / semanas_rest)
