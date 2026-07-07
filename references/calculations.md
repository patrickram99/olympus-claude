# Olympus CRM — Calculation cheatsheet

## Table of contents

1. Wilson lower bound 95%
2. Proportional cost attribution (FTE equivalents)
3. Sensitivity engine — full cost model
4. Break-even calculations
5. Quadrant analysis for country prioritization
6. Worked example: imbpepkeyacc05261

---

## 1. Wilson lower bound 95% — ranking conversion rates with mixed sample sizes

**Why**: crude TC (matriculados / leads) is unstable for small samples. An asesor with 1/3 = 33% will outrank one with 100/2000 = 5% even though the second has far more evidence. The Wilson lower bound is the smallest p that's still consistent with the observed data at 95% confidence — it penalizes small samples appropriately.

**Formula**:
```
z = 1.96  (for 95% CI)
p = success / n
center = p + z² / (2n)
margin = z × √( p(1-p)/n + z²/(4n²) )
denom = 1 + z²/n
wilson_lb = max(0, (center - margin) / denom)
```

**JavaScript**:
```js
function wilsonLB(success, n, z = 1.96) {
  if (n <= 0) return 0;
  const p = success / n;
  const denom = 1 + (z * z) / n;
  const center = p + (z * z) / (2 * n);
  const margin = z * Math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n));
  return Math.max(0, (center - margin) / denom);
}
```

**Python**:
```python
def wilson_lb(success, n, z=1.96):
    if n <= 0: return 0.0
    p = success / n
    denom = 1 + z*z/n
    center = p + z*z/(2*n)
    margin = z * ((p*(1-p)/n) + z*z/(4*n*n))**0.5
    return max(0.0, (center - margin)/denom)
```

**Usage rules**:
- Always show TC and Wilson side by side.
- Rank by Wilson, not TC.
- Apply a minimum-sample threshold separately (the user typically defaults to 30 leads for asesores, 100 for products, no minimum for countries).

**Worked example**:
| Asesor | Leads | Matric | TC crudo | Wilson LB |
|---|---|---|---|---|
| A | 3 | 1 | **33.3%** | 1.8% |
| B | 2000 | 100 | 5.0% | **4.1%** |

Asesor B is the real winner — its 5% is much better established than A's 33%.

---

## 2. Proportional cost attribution — FTE equivalents

**The problem**: Asesor X worked 200 leads of product P out of their 2000 total leads. The salary base is 565 PEN/mes. How much of that salary "belongs to" product P?

**The wrong answer**: 565 PEN (the full salary). This overcounts because the asesor also worked 1800 other leads on dozens of products.

**The right answer**: 565 × (200/2000) = 56.5 PEN.

**Algorithm**:
1. For the product of interest, get `leadsProducto[asesor]` for each asesor that touched it.
2. For the same period, get each of those asesores' `leadsTotal[asesor]` across all products.
3. For each asesor: `peso[a] = leadsProducto[a] / leadsTotal[a]` (0 ≤ peso ≤ 1).
4. `FTE_equivalentes = Σ peso[a]` — usually 1-5 for a single product, even if 100+ asesores touched it.
5. `costoSalarial = salarioBasePEN × FTE_equivalentes`.

**Why FTE equivalents matter**: they show the *true* labor cost. A product with 100 asesores at 5% time each costs the same as 5 asesores full-time — but you might wrongly think the first is 20× more expensive if you don't proportion.

**Edge cases**:
- Asesor with `leadsTotal = 0`: ignore (would divide by zero; also impossible if they have leadsProducto > 0).
- If period is very short, the ratio may be noisy. Either use a longer baseline period for `leadsTotal` or warn the user.

---

## 3. Sensitivity engine — full cost model

**Inputs** (defaults from `.env` or panel sliders):
| Parameter | Default | Description |
|---|---|---|
| `salarioBasePEN` | 565 | Monthly base salary per asesor (PEN) |
| `cplUSD` | 0.20 | Cost per lead generated (USD) |
| `comisionAsesorPct` | 0.10 | 10% of cobrado, only paid to convertidores |
| `comisionAdminPct` | 0.10 | 10% of cobrado, administrative overhead |
| `docenteUSD` | 1440 | Fixed payment to teaching staff per cohort (USD) |
| `usdPenRate` | 3.78 | USD → PEN conversion |
| `cobranzaEfectividad` | observed | `cobrado / comprometido` ratio |

**Baseline (from DB)**:
- `leads` — total leads on product
- `matriculados` — sales closed
- `fteEquivalentes` — from FTE attribution
- `montoComprometidoUSD` — sum of `CobranzaPlan.Total`
- `montoCobradoUSD` — sum of `CobranzaPago.Monto`

**Costos en PEN**:
```
salarios          = salarioBasePEN × fteEquivalentes
docentes_PEN      = docenteUSD × usdPenRate
cpl_PEN           = leads × cplUSD × usdPenRate
cobrado_PEN       = montoCobradoUSD × usdPenRate
comisionAsesores  = cobrado_PEN × comisionAsesorPct
admin             = cobrado_PEN × comisionAdminPct
costoTotal        = salarios + docentes_PEN + cpl_PEN + comisionAsesores + admin
```

**P&L**:
```
ingreso_PEN       = cobrado_PEN
margen_PEN        = ingreso_PEN - costoTotal
margenPct         = margen_PEN / ingreso_PEN
costoPorLead      = costoTotal / leads
costoPorMatricula = costoTotal / matriculados
ingresoPorMatric  = ingreso_PEN / matriculados
```

**Two scenarios to ALWAYS show**:
- **Comprometido pleno**: ingreso = `montoComprometidoUSD × usdPenRate` (asume 100% cobranza eventual).
- **Cobrado actual**: ingreso = `montoCobradoUSD × usdPenRate` (lo realmente recibido a la fecha).

The gap between them is the cobranza pendiente — a real lever the user can move.

---

## 4. Break-even calculations

**Break-even TC** — qué TC necesitaríamos para cubrir costos:
```
ingresoPorMatricula = costoBaseProducto × usdPenRate × cobranzaEfectividad
                      × (1 - comisionAsesorPct - comisionAdminPct)
costoFijo           = salarios + docentes_PEN + cpl_PEN
matricBreakeven     = costoFijo / ingresoPorMatricula
tcBreakeven         = matricBreakeven / leads
```

**CPL máximo rentable** — cuánto puedo subir el CPL antes de perder plata:
```
margen_actual = ingreso_PEN - costoTotal
margen_por_lead_extra = (margen_actual + cpl_PEN) / leads
cplMaxUSD = margen_por_lead_extra / usdPenRate
```

(Esto asume que subir el CPL no cambia volumen — en la realidad sube y eso lo cambia. Usar como upper bound.)

**Leads mínimos viables** — mínimo de leads para amortizar costos fijos a la TC observada:
```
ingresoPorLead = (matriculados / leads) × ingresoPorMatricula
costoVarPorLead = cpl_PEN/leads + comisionPorLead + adminPorLead
leadsMinViables = costoFijo / (ingresoPorLead - costoVarPorLead)
```

---

## 5. Quadrant analysis for country prioritization (BCG-style)

Plot países en un scatter:
- **X-axis**: volumen de leads
- **Y-axis**: Wilson lower bound 95% de la TC

Divisiones (usar mediana de cada eje como umbral):
| Cuadrante | Descripción | Recomendación |
|---|---|---|
| Alto vol + Alto Wilson | "Estrella" | Invertir más, mercado probado |
| Alto vol + Bajo Wilson | "Vaca / Problema" | Investigar por qué la conversión es baja, optimizar funnel |
| Bajo vol + Alto Wilson | "Pregunta" | Lanzar piloto para validar (la muestra es chica) |
| Bajo vol + Bajo Wilson | "Perro" | No invertir |

**Caveats**:
- Para "Bajo vol + Alto Wilson" con n < 30, el Wilson LB ya es bajo — el cuadrante se vacía solo. Eso es deseable.
- Considera también costo de adquisición por país (a veces CPL más alto justifica volumen menor).

---

## 6. Worked example: imbpepkeyacc05261 (PEP Key Account Manager - Mayo)

Datos verificados:
- `producto_id` = 381
- `leads` = 3,715
- `asesoresQueTrabajaron` = 116
- `matriculados` = 12
- `montoComprometidoUSD` = 6,364.53
- `montoCobradoUSD` = 4,226.86

FTE attribution (Σ pesos sobre los 116 asesores):
- `fteEquivalentes` = **3.29** (calculado en sesión real)

Cálculo de costos con parámetros default + tipo de cambio 3.78:

| Concepto | Fórmula | PEN |
|---|---|---:|
| Salarios | 565 × 3.29 | 1,861.27 |
| Docentes | 1440 × 3.78 | 5,443.20 |
| CPL | 3715 × 0.20 × 3.78 | 2,808.54 |
| Comisión asesores | 4226.86 × 0.10 × 3.78 | 1,597.75 |
| Admin | 4226.86 × 0.10 × 3.78 | 1,597.75 |
| **Costo total** |  | **13,308.51** |
| Ingreso (cobrado) | 4226.86 × 3.78 | 15,977.53 |
| **Margen** |  | **+2,669.02** |

Métricas derivadas:
- Costo por lead: **3.58 PEN**
- Costo por matrícula: **1,109.04 PEN**
- Ingreso por matrícula: **1,331.46 PEN**
- Margen por matrícula: **+222 PEN** (16.7%)

Si todos los matriculados cumplen el plan ($6,364.53 → 24,058 PEN):
- Margen potencial: **+10,750 PEN** (45%)

Use este ejemplo como ground truth para validar implementaciones del engine de sensibilidad.
