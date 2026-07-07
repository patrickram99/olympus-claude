# Rollout Bot de IA — Plan de Rentabilidad Comprometida

**Meta:** USD 5.000 de margen comprometido
**Ventana:** 15 → 30 de junio de 2026 (15 días)
**Programas:** Controller Financiero · Analista de Datos con Power BI y Python · Customer Experience Manager
**Fuente de datos:** Olympus CRM (IMB / IESL) — montos comprometidos reales por matrícula.

---

## 1. Objetivo del experimento

Lanzar un bot de IA (WhatsApp/Meta + API de IA) que atiende conversaciones de leads y los convierte a matrícula, **reemplazando el trabajo del asesor humano en la captación inicial**.

Objetivo doble:
- **(a)** Generar **USD 5.000 de margen comprometido** en la ventana.
- **(b)** Validar si la reducción de costo del bot vuelve rentable **Analista de Datos con Power BI y Python**, que con asesor humano pierde plata en sus dos últimas ediciones.

---

## 2. Supuestos económicos

| Supuesto | Valor |
|---|---|
| TC global con bot | **0,30 %** (3 matrículas por 1.000 leads) |
| Costo por conversación de bot (Meta + API IA) | **USD 0,15** por lead (1 conversación = 1 lead) |
| CPL Controller | USD 0,50 |
| CPL Customer | USD 0,50 |
| CPL Analista de Datos | USD 0,20 |
| Comisiones | 20 % sobre comprometido (10 % asesor + 10 % admin) |
| Salario de asesor | **Excluido** (lo reemplaza el bot) |
| Docente | **Excluido** (cohortes ya abiertas) |
| Tipo de cambio | USD/PEN = 3,78 |

**Costo por lead resultante:**

| Programa | CPL | + Bot | **Costo/lead** |
|---|---|---|---|
| Controller Financiero | 0,50 | 0,15 | **0,65** |
| Customer Experience Mgr | 0,50 | 0,15 | **0,65** |
| Analista de Datos | 0,20 | 0,15 | **0,35** |

**Ingreso comprometido por matrícula** (de los P&L reales, USD):

| Programa | Ingreso/matrícula |
|---|---|
| Controller Financiero | 602 |
| Customer Experience Mgr | 506 |
| Analista de Datos | 322 |

---

## 3. Unidad económica: contribución por lead

```
contrib_por_lead = TC × ingreso_por_matrícula × (1 − 0,20) − (CPL + 0,15)
```

| Programa | TC × R × 0,8 | − Costo/lead | **Contrib/lead** | ROI sobre gasto |
|---|---|---|---|---|
| Controller Financiero | 1,445 | 0,65 | **0,795** | 122 % |
| Analista de Datos | 0,774 | 0,35 | **0,424** | 121 % |
| Customer Experience Mgr | 1,215 | 0,65 | **0,565** | 87 % |

**Detalle de cálculo:**
- Controller: `0,003 × 602 × 0,8 = 1,445` → `1,445 − 0,65 = 0,795`
- Analista: `0,003 × 322 × 0,8 = 0,774` → `0,774 − 0,35 = 0,424`
- Customer: `0,003 × 506 × 0,8 = 1,215` → `1,215 − 0,65 = 0,565`

**Hallazgo del experimento:** con el bot, **Analista de Datos pasa a ser rentable** (USD 0,42/lead, ROI 121 %) — la reducción de costo sí lo arregla. Controller es el más eficiente; Customer queda último por su ticket bajo frente a un CPL alto.

**Prioridad de inversión por ROI:** Controller > Analista de Datos > Customer.

---

## 4. Plan recomendado para USD 5.000 de margen comprometido

| Programa | Leads | Matríc. esp. (×0,3 %) | Comprometido | − Comis. 20 % | − Gasto leads | **Margen** |
|---|---|---|---|---|---|---|
| Controller Financiero | 3.500 | 10,5 | 6.321 | −1.264 | −2.275 | **2.782** |
| Analista de Datos | 3.000 | 9,0 | 2.898 | −580 | −1.050 | **1.268** |
| Customer Experience Mgr | 2.000 | 6,0 | 3.036 | −607 | −1.300 | **1.129** |
| **TOTAL** | **8.500** | **25,5** | **12.255** | **−2.451** | **−4.625** | **5.179** |

- Margen total: **USD 5.179** (buffer ~USD 179 sobre la meta).
- **Ritmo diario:** 8.500 leads / 15 días ≈ **567 leads/día**
  - Controller: 233/día
  - Analista de Datos: 200/día
  - Customer: 133/día

---

## 5. Umbrales de break-even (TC mínima por programa)

TC a la que el margen por lead = 0 (no se pierde dinero):

```
TC_breakeven = (CPL + 0,15) / (ingreso_por_matrícula × 0,8)
```

| Programa | TC break-even | Margen de seguridad vs. 0,30 % |
|---|---|---|
| Controller Financiero | 0,135 % | 2,2× |
| Analista de Datos | 0,136 % | 2,2× |
| Customer Experience Mgr | 0,161 % | 1,9× |

Si la TC real cae por debajo de estos valores, ese programa empieza a perder dinero → reasignar presupuesto al de mejor ROI (Controller).

---

## 6. Roadmap 15 → 30 de junio

| Fase | Días | Acción |
|---|---|---|
| Setup | -3 a 0 | Integración bot ↔ Meta/API, configuración de prompts, pruebas internas |
| Piloto | 1–2 | Lanzamiento controlado, validar TC real vs. 0,30 % |
| Escalado | 3–10 | Subir pauta a ritmo de 567 leads/día, monitoreo diario |
| Checkpoints | cada 3 días | Medir TC real, costo/lead real, reasignar presupuesto por ROI |
| Corte y medición | 30 jun | Cierre, medición de margen comprometido vs. meta USD 5.000 |

**KPI de éxito:** margen comprometido ≥ USD 5.000 al 30 de junio.

---

## 7. Sensibilidad: ¿y si abrimos cohortes nuevas?

Si los 3 cursos arrancan cohorte nueva en esta ventana, suma el costo fijo de docente:

- Docente: **3 × USD 1.440 = USD 4.320** de costo fijo adicional.
- Contribución requerida: `5.000 + 4.320 = USD 9.320`.
- Leads necesarios: ~**15.300** (vs. 8.500) → ~1.020 leads/día (agresivo).

Por eso el plan base asume **cohortes ya abiertas**.

---

## 8. Caveats

- **TC 0,30 %** es un supuesto de entrada, no un dato observado del bot — los checkpoints cada 3 días sirven para corregirlo.
- Las matrículas esperadas son fracciones (10,5 · 9,0 · 6,0): en muestras chicas el resultado real tendrá alta varianza.
- "Comprometido" asume el pago de todas las cuotas futuras del plan de cobranza (riesgo de mora real no descontado).
- El modelo asume 1 conversación de bot = 1 lead; si el bot necesita varias conversaciones por lead, el costo de USD 0,15 sube proporcionalmente.
