"""
Business calculations: Wilson lower bound, FTE attribution, sensitivity engine.
Pure functions — no DB, no IO. Testable in isolation.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass


def wilson_lb(success: int, n: int, z: float = 1.96) -> float:
    """
    Wilson lower bound at confidence level z (default 95%).
    Use this to rank conversion rates with mixed sample sizes.
    """
    if n <= 0:
        return 0.0
    # Clamp p to [0,1]: un asesor puede cerrar leads asignados a otros, así que
    # matrículas (success) puede superar sus leads (n) → p>1 → varianza negativa
    # bajo la raíz. Lo tratamos como p=1 (cierre perfecto observado).
    p = min(1.0, max(0.0, success / n))
    denom = 1 + (z * z) / n
    center = p + (z * z) / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))
    return max(0.0, (center - margin) / denom)


def wilson_ub(success: int, n: int, z: float = 1.96) -> float:
    """
    Wilson UPPER bound at confidence level z (default 95%).

    Ranking de "peores"/menos eficientes: el lower bound deja a TODOS los asesores
    con 0 matrículas empatados en 0,0 sin importar cuántos leads quemaron (0/30 y
    0/1376 dan el mismo LB). El upper bound sí los distingue: cuanto mayor el
    volumen sin conversión, más ESTRECHO (bajo) es el UB → 0/1376 tiene un UB muy
    inferior a 0/30. Ordenar por UB ascendente sube al tope de los peores a quien
    más leads desperdició con poca o ninguna venta, que es la verdadera ineficiencia.
    """
    if n <= 0:
        return 1.0
    p = min(1.0, max(0.0, success / n))
    denom = 1 + (z * z) / n
    center = p + (z * z) / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))
    return min(1.0, (center + margin) / denom)


def fte_equivalents(leads_in_product: dict[int, int], leads_total: dict[int, int]) -> float:
    """
    Sum of per-asesor weights, where weight_a = leads_a_in_product / leads_a_total.
    Returns the number of full-time equivalents dedicated to the product.
    """
    total = 0.0
    for asesor_id, lp in leads_in_product.items():
        lt = leads_total.get(asesor_id, 0)
        if lt > 0:
            total += lp / lt
    return total


@dataclass
class CostParams:
    salario_base_pen: float = 565.0
    cpl_usd: float = 0.20
    comision_asesor_pct: float = 0.10
    comision_admin_pct: float = 0.10
    docente_usd: float = 1440.0
    usd_pen: float = 3.78

    @classmethod
    def from_env(cls) -> "CostParams":
        """Resuelve los parámetros de negocio: .env > config.toml > default."""
        from . import config
        return cls(
            salario_base_pen=config.get_float("costos", "salario_base_pen", "SALARIO_BASE_PEN", 565),
            cpl_usd=config.get_float("costos", "cpl_usd", "CPL_USD", 0.20),
            comision_asesor_pct=config.get_float("costos", "comision_asesor_pct", "COMISION_ASESOR_PCT", 0.10),
            comision_admin_pct=config.get_float("costos", "comision_admin_pct", "COMISION_ADMIN_PCT", 0.10),
            docente_usd=config.get_float("costos", "docente_usd", "DOCENTE_USD", 1440),
            usd_pen=config.get_float("costos", "usd_pen", "USD_PEN_RATE", 3.78),
        )


@dataclass
class ProductBaseline:
    leads: int
    matriculados: int
    fte: float
    monto_comprometido_usd: float
    monto_cobrado_usd: float
    costo_base_usd: float = 0.0  # precio de lista del producto


@dataclass
class PnLResult:
    salarios: float
    docentes: float
    cpl: float
    comision_asesores: float
    admin: float
    costo_total: float
    ingreso_pen: float
    margen_pen: float
    margen_pct: float
    costo_por_lead: float | None  # None si no hubo leads
    costo_por_matricula: float | None  # None si no hubo matrículas
    ingreso_por_matricula: float | None  # None si no hubo matrículas
    breakeven_tc: float | None
    breakeven_cpl_usd: float | None
    breakeven_leads_min: float | None

    def to_dict(self) -> dict:
        return {k: round(v, 2) if isinstance(v, float) and v is not None else v for k, v in self.__dict__.items()}


def compute_pnl(b: ProductBaseline, p: CostParams, ingreso_mode: str = "cobrado") -> PnLResult:
    """
    Compute the P&L of a product given baseline observations and cost parameters.
    ingreso_mode: 'cobrado' (use actually-paid) or 'comprometido' (assume 100% of plans paid).
    """
    base_usd = b.monto_cobrado_usd if ingreso_mode == "cobrado" else b.monto_comprometido_usd
    ingreso_pen = base_usd * p.usd_pen

    salarios = p.salario_base_pen * b.fte
    docentes = p.docente_usd * p.usd_pen
    cpl = b.leads * p.cpl_usd * p.usd_pen
    comision_asesores = ingreso_pen * p.comision_asesor_pct
    admin = ingreso_pen * p.comision_admin_pct
    costo_total = salarios + docentes + cpl + comision_asesores + admin
    margen_pen = ingreso_pen - costo_total
    margen_pct = (margen_pen / ingreso_pen) if ingreso_pen > 0 else 0.0
    # Break-even
    costo_fijo = salarios + docentes + cpl
    ingreso_por_matric_unit = (
        b.costo_base_usd * p.usd_pen * (1 - p.comision_asesor_pct - p.comision_admin_pct)
    ) if b.costo_base_usd > 0 else (ingreso_pen / b.matriculados if b.matriculados else 0)

    if ingreso_por_matric_unit > 0:
        matric_be = costo_fijo / ingreso_por_matric_unit
        tc_be = matric_be / b.leads if b.leads > 0 else None
    else:
        tc_be = None

    # CPL máximo rentable: cuánto puedo subir CPL antes de margen = 0
    if b.leads > 0:
        # margen + cpl = costo evitable si elimino CPL; ingreso_max_var_cost = margen + cpl
        cpl_max_pen = (margen_pen + cpl) / b.leads
        cpl_max_usd = cpl_max_pen / p.usd_pen if cpl_max_pen > 0 else 0
    else:
        cpl_max_usd = None

    return PnLResult(
        salarios=salarios,
        docentes=docentes,
        cpl=cpl,
        comision_asesores=comision_asesores,
        admin=admin,
        costo_total=costo_total,
        ingreso_pen=ingreso_pen,
        margen_pen=margen_pen,
        margen_pct=margen_pct,
        costo_por_lead=costo_total / b.leads if b.leads else None,
        costo_por_matricula=costo_total / b.matriculados if b.matriculados else None,
        ingreso_por_matricula=ingreso_pen / b.matriculados if b.matriculados else None,
        breakeven_tc=tc_be,
        breakeven_cpl_usd=cpl_max_usd,
        breakeven_leads_min=None,  # se puede agregar luego si se necesita
    )
