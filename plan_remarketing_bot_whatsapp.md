# Remarketing Bot WhatsApp a Perdidos — Plan de Rentabilidad (v3, calibrado con piloto real)

**Veredicto:** Rentable. Con el portafolio ampliado (7 programas), el margen comprometido esperado es **~USD 2.670** sobre una inversión de USD 3.470 — supera 2,6× la meta mínima de USD 1.000.
**Cambio clave v3:** Analista de Datos (PyBI y Fabric) **sale del plan** (pierde plata con las tasas actuales) y entran 5 programas con mejor tasa Potencial→Matriculado detectados en Olympus.
**Fuente de datos:** Piloto real del bot (339 mensajes efectivos, jul-2026) + Olympus CRM (universo de perdidos, Pot→Mat y ticket comprometido reales por familia).

---

## 1. Modelo de costo por mensaje (desglosado Meta vs IA)

| Componente | Base | Costo |
| :---- | :---- | :---- |
| **Meta (WhatsApp API)** — plantilla de marketing | por mensaje efectivo enviado (dato real piloto: 37,63/339) | **USD 0,1110 / mensaje** |
| **IA (Gemini API)** — bot conversacional | solo cuando el contacto responde (5,3 % de los mensajes) · USD 0,20/conversación | **USD 0,0106 / mensaje** |
| **Total** | | **USD 0,1216 / mensaje efectivo** |

- La IA pesa < 9 % del costo: el driver es Meta.
- Sensibilidad: si Gemini costara USD 0,40/conversación (escenario exagerado), el costo sube a 0,1322/mensaje y el margen total del plan baja ~USD 300 (de 2.670 a ~2.370). No cambia ninguna decisión de portafolio.

## 2. Funnel observado (piloto, 339 mensajes efectivos)

- Tasa de respuesta: **5,3 %** (18 conversaciones) · Tiempo de respuesta 11 s
- Potenciales reingresados al CRM: **2** → **0,59 % por mensaje efectivo** (11,1 % de las conversaciones)
- Ventas directas del bot: 0 — el cierre lo hace el asesor desde Potencial
- Costo real por potencial reingresado: **USD 18,80**

## 3. Selección de programas (screening de todas las familias en Olympus)

Se evaluaron todas las familias con ≥500 perdidos contactables. Criterio: margen/mensaje = 0,59 % × Pot→Mat × ticket × 0,8 − 0,1216 > 0, sosteniéndose positivo también en el límite inferior Wilson 95 % de la Pot→Mat.

**Entran (7):**

| Programa | Perdidos contactables (únicos) | De ellos <3 meses | Pot→Mat real | Ticket USD | Margen/mensaje |
| :---- | :---- | :---- | :---- | :---- | :---- |
| PAE Gerente de Planta: IA, Power BI y Gestión Integral | 1.380 | 1.399* | **17,1 %** (18/105) | 592 | **+0,357** |
| CEP Gobernanza IA & Gestión Sistemas ISO/IEC 42001 | 995 | 654 | **14,1 %** (13/92) | 444 | **+0,174** |
| PAE Gerencia de Producción y Transformación 4.0 | 1.758 | 929 | 8,7 % (17/196) | 707 | **+0,168** |
| PEP People Analytics Manager | 2.806 | 1.429 | 9,6 % (28/293) | 507 | **+0,107** |
| PEP Customer Experience Manager | 2.741 | 2.194 | 8,9 % (19/213) | 498 | **+0,088** |
| PAE Gerente en Mantenimiento | 6.689 | 2.968 | 5,3 % (52/973) | 755 | **+0,069** |
| Controller Financiero | 12.165 | 6.262 | 5,6 % (94/1.675) | 679 | **+0,058** |

\* El conteo <3m es por oportunidad y puede superar a personas únicas cuando hay repetidos.

**Salen:** Analista de Datos PyBI (margen −0,034/mensaje: Pot→Mat 3,9 % con ticket 422) · Analista de Datos Fabric (−0,081) · también quedan fuera por margen nulo/negativo: Key Account (−0,005), Gestión Proyectos TI (−0,011), Finanzas Corp Power BI (−0,013), Gestión RRHH (+0,002, sin colchón).

## 4. Plan recomendado — 28.534 mensajes, margen esperado USD 2.670

| Programa | Mensajes | Meta (USD) | IA (USD) | Potenciales esp. | Matríc. esp. | Comprometido | Margen (USD) |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Gerente de Planta IA/PBI | 1.380 | −153 | −15 | 8,1 | 1,4 | 826 | **+493** |
| Gobernanza IA ISO 42001 | 995 | −110 | −11 | 5,9 | 0,8 | 368 | **+173** |
| Producción y Transf. 4.0 | 1.758 | −195 | −19 | 10,4 | 0,9 | 636 | **+295** |
| People Analytics Mgr | 2.806 | −311 | −30 | 16,6 | 1,6 | 801 | **+300** |
| Customer Experience Mgr | 2.741 | −304 | −29 | 16,2 | 1,4 | 719 | **+242** |
| Gerente en Mantenimiento | 6.689 | −742 | −71 | 39,5 | 2,1 | 1.592 | **+460** |
| Controller Financiero | 12.165 | −1.350 | −129 | 71,8 | 4,0 | 2.734 | **+708** |
| **TOTAL** | **28.534** | **−3.167** | **−303** | **168** | **12,3** | **7.675** | **+2.671** |

- Margen = comprometido × 0,8 (comisiones 20 %) − Meta − IA.
- **Gasto total: USD 3.470 → Meta USD 3.167 (91 %) · IA USD 303 (9 %, ~1.515 conversaciones a 0,20).**
- Universo one-shot: agotados los 28.534, el volumen nuevo depende de la acumulación mensual de perdidos.

## 5. Break-even por programa (potenciales por mensaje mínimos)

| Programa | Break-even | Margen de seguridad vs. 0,59 % observado |
| :---- | :---- | :---- |
| Gerente de Planta IA/PBI | 0,15 % | 3,9× |
| Gobernanza IA ISO 42001 | 0,24 % | 2,5× |
| Producción y Transf. 4.0 | 0,25 % | 2,4× |
| People Analytics Mgr | 0,31 % | 1,9× |
| Customer Experience Mgr | 0,34 % | 1,7× |
| Gerente en Mantenimiento | 0,38 % | 1,6× |
| Controller Financiero | 0,40 % | 1,5× |

Los dos programas grandes (Mantenimiento y Controller) son los de menor colchón: son los que decide el checkpoint.

## 6. Rollout por tramos

| Tramo | Mensajes | A quién | Checkpoint |
| :---- | :---- | :---- | :---- |
| 1 | 9.680 (~USD 1.177) | Las 5 familias de mayor margen/mensaje: Planta IA + Gobernanza + Prod. Transf. + People Analytics + Customer (priorizando perdidos <3 meses) | Al cierre: **≥ 39 potenciales (0,40 %) → tramo 2 completo** · 30–38 → revisar plantilla, lanzar solo Mantenimiento · **< 30 (0,31 %) → parar** |
| 2 | 18.854 (~USD 2.293) | Gerente en Mantenimiento + Controller Financiero (primero <3 meses) | Medir la Pot→Mat real de los reingresados del tramo 1 vs. las tasas históricas de §3 |

El tramo 1 concentra el mejor ROI y sirve para re-estimar el 0,59 % (hoy sale de solo 2 casos, IC 95 %: 0,16 %–2,1 %) antes de comprometer el 66 % restante del presupuesto.

## 7. Caveats

- **n=2 potenciales** en el piloto: el 0,59 % es el supuesto más frágil; el diseño por tramos existe para eso.
- Las Pot→Mat de Gerente de Planta (18/105) y Gobernanza ISO (13/92) tienen muestras chicas; aun en su límite inferior Wilson 95 % (11,1 % y 8,5 %) el margen/mensaje sigue positivo (+0,19 y +0,06).
- La Pot→Mat aplicada es la de potenciales **orgánicos**; un perdido reingresado puede convertir peor. El checkpoint del tramo 2 la mide con datos propios.
- El piloto no separó tasas por programa: asumimos que el 0,59 % transfiere igual a todas las familias.
- "Comprometido" no descuenta mora (efectividad de cobranza histórica 55–90 %); el margen cobrado será menor y llega en cuotas.
- 1 mensaje efectivo por persona. Personas perdidas en 2+ familias reciben 1 solo mensaje, asignadas al programa de mayor margen/mensaje.
- Excluir siempre `Desuscrito = 1` (ya descontado en los universos).
- IA a USD 0,20/conversación es el escenario realista del PM; a 0,40 el plan sigue en pie (§1).
