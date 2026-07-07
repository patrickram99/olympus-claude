# Olympus CRM — Schema reference

## Table of contents

1. Soft-delete and conventions
2. `adm.Oportunidad` (fact: leads)
3. `adm.HistorialEstado` (fact: state transitions)
4. `adm.Personal` (dim: asesores)
5. `adm.Producto` (dim: cursos)
6. `adm.PotencialCliente`, `adm.Persona`, `mdm.Pais` (lead's contact + country path)
7. `adm.CobranzaPlan`, `adm.CobranzaPago` (revenue)
8. `adm.Estado` (lead state enum), `adm.Tipo` (typologies)
9. Soft-delete + active filters quick reference
10. Join graph

## 1. Soft-delete and conventions

Every business-fact table has an `Estado bit` column where `1 = active` and `0 = deleted`. Treat any query that omits `Estado = 1` filtering on a joined table as a bug.

Datetimes are local server time (Lima, UTC-5). `FechaCreacion` is creation, `FechaModificacion` is last touch. There is no separate audit log — modification tracking is via these timestamps + `UsuarioModificacion`.

## 2. `adm.Oportunidad` — the lead

| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | NOT `IdOportunidad`. Just `Id`. |
| `IdProducto` | int FK | → `adm.Producto.Id` |
| `IdPersonal` | int FK | Asesor currently "owning" the lead. Can be NULL. |
| `IdPotencialCliente` | int FK | → `adm.PotencialCliente.Id`. **Populated in ~99% of rows.** |
| `IdPersona` | int FK | → `adm.Persona.Id`. **Populated in only ~5% of rows.** Do not use for joins. |
| `Estado` | bit | 1 = active, 0 = soft-deleted. |
| `FechaCreacion` | datetime | When the lead entered the CRM. |
| `Origen` | varchar | **Canal** de captación, NO la campaña. Valores reales: `Linkedin` (~99%), `Manual`, `Wordpress`, `FormularioWeb`, `NULL`. El nombre de campaña sólo existe para LinkedIn en `adm.LinkedIn_Lead.FormName` (ver §11). |
| `CodigoLanzamiento` | varchar | Mirror of the product's launch code. |

Volume: ~211K rows total, ~210K active.

## 3. `adm.HistorialEstado` — the fact of state transitions

Each row is one change of state for one oportunidad. This is the most important table.

| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | |
| `IdOportunidad` | int FK | → `Oportunidad.Id` |
| `IdPersonal` | int FK | Asesor who executed the change. **Use this.** Populated in 444K of 463K rows. |
| `IdAsesor` | int FK | LEGACY column. Populated for older rows only. Differs from `IdPersonal` when both present. Do not use. |
| `IdEstado` | int FK | → `adm.Estado.Id`. The destination state. |
| `CantidadLlamadasContestadas` | int | **Cumulative count** for this Oportunidad up to and including this row. |
| `CantidadLlamadasNoContestadas` | int | Same — cumulative. |
| `FechaCreacion` | datetime | Timestamp of the change. |
| `Estado` | bit | Soft-delete flag. |

Key derived patterns:
- **Calls made by asesor X in period P** = sum over rows where `FechaCreacion ∈ P` and `IdPersonal = X` of `MAX(0, currentValue - LAG(currentValue) OVER (PARTITION BY IdOportunidad ORDER BY FechaCreacion, Id))`.
- **Current state of a lead** = row with `MAX(FechaCreacion)` per `IdOportunidad`.
- **Lead first assigned to asesor X** = row with `MIN(FechaCreacion)` per `(IdOportunidad, IdPersonal)`.
- **Lead matriculated by asesor X** = row with `IdEstado = 3` and `IdPersonal = X`; if multiple, take `MIN(FechaCreacion)`.

Volume: ~463K rows (Dec 2025 → present).

## 4. `adm.Personal` — asesores

| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | |
| `Nombres`, `Apellidos` | varchar | Concat for display. Some have leading/trailing spaces — `LTRIM(RTRIM())` recommended. |
| `IdPais` | int FK | → `mdm.Pais.Id`. Asesor's residence country. **NOT the lead's country.** |
| `IdTipoJornada` | int FK | → `adm.Tipo.Id`. 31 = Tiempo Completo, 32 = Tiempo Parcial. |
| `FechaIngreso` | date | Hire date. **Some rows have years like 2001 or 2005 — clearly pre-CRM. Treat > 365-day deltas as outliers when computing time-to-first-sale.** |
| `Estado` | bit | 1 = active. |
| `Cesado` | bit | 1 = no longer with company. Filter `ISNULL(Cesado, 0) = 0` for current staff. |
| `IdTipoJornada` | int | 31 / 32 (see above). |

Volume: 248 active asesores in 31/32 jornadas.

Display name pattern:
```sql
REPLACE(LTRIM(RTRIM(ISNULL(p.Nombres,'') + ' ' + ISNULL(p.Apellidos,''))), ',', '~~') AS Nombre
```

## 5. `adm.Producto` — cursos

| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | |
| `Nombre` | varchar | Name. Often includes the launch month (e.g., "PEP Controller Financiero - Mayo"). |
| `CodigoLanzamiento` | varchar | Machine-readable code, e.g., `imbpepkeyacc05261` (PEP Key Account Manager, May 2026 release 1). |
| `CostoBase` | decimal | USD list price. Actual sale may differ (descuentos). |
| `PersonalCreacion` | int FK | → `Personal.Id`. **Encargado del producto** — the product owner, distinct from the asesores who sell it. |
| `EstadoProductoTipoId` | int FK | → `adm.Tipo.Id` (categoria='EstadoProducto'). 17=Piloto, 18=En curso, 19=Preventa, 20=En venta, 21=Grupo completo, 13=Cancelado, 14=Postergado, 15=Finalizado, 16=No llamar nuevos. |
| `Estado` | bit | Soft-delete. |
| `FechaInicio`, `FechaFin` | datetime | Course dates. |

Naming conventions:
- `CEP` = Curso de Especialización Profesional
- `PEP` = Programa de Especialización Profesional
- `PAE` = Programa de Alta Especialización
- `PAD` = Programa de Alta Dirección

## 6. Country path: `Oportunidad → PotencialCliente → Persona → Pais`

This is the only reliable path to the lead's country.

```
adm.Oportunidad op
  INNER JOIN adm.PotencialCliente pc ON pc.Id = op.IdPotencialCliente
  INNER JOIN adm.Persona per         ON per.Id = pc.IdPersona
  INNER JOIN mdm.Pais pa             ON pa.Id  = per.IdPais
```

`adm.PotencialCliente`:
| Column | Type |
|---|---|
| `Id` | int PK |
| `IdPersona` | int FK → `Persona.Id` |
| `Estado` | bit |

`adm.Persona`:
| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | |
| `IdPais` | int FK | → `mdm.Pais.Id`. The country we want. |
| `Nombres`, `Apellidos`, `Celular`, `Correo` | | Contact fields. |
| `PrefijoPaisCelular` | varchar | Phone prefix (alternative country hint if `IdPais` is NULL). |
| `Estado` | bit | |

`mdm.Pais`:
| Column | Type |
|---|---|
| `Id` | int PK |
| `Nombre` | varchar |

## 7. Revenue: `CobranzaPlan` + `CobranzaPago`

When a lead matriculates, one `CobranzaPlan` is created (the agreed amount + installment plan). As the student pays, `CobranzaPago` rows accumulate against that plan.

`adm.CobranzaPlan`:
| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | |
| `IdOportunidad` | int FK | → `Oportunidad.Id` |
| `IdProducto` | int FK | Redundant with `Oportunidad.IdProducto` but present. |
| `Total` | decimal | **Monto comprometido**. USD. |
| `NumCuotas` | int | |
| `FechaInicio` | datetime | |
| `Estado` | bit | |

`adm.CobranzaPago`:
| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | |
| `IdCobranzaPlan` | int FK | → `CobranzaPlan.Id` |
| `Monto` | decimal | **Monto cobrado** en esta cuota. USD. |
| `FechaPago` | datetime | |
| `Estado` | bit | |

Derived:
- `MontoComprometido = SUM(CobranzaPlan.Total WHERE Estado=1)` (for matriculated oportunidades)
- `MontoCobrado = SUM(CobranzaPago.Monto WHERE Estado=1)` (effective revenue received)
- `EfectividadCobranza = MontoCobrado / MontoComprometido` (usually 0.55 – 0.90)

## 8. Enums

### `adm.Estado` (lead status) — Categoria implicit, no Categoria column on this table
| Id | Nombre | Pipeline meaning |
|---|---|---|
| 1 | Registrado | New lead |
| 2 | No calificado | Disqualified |
| 3 | Matriculado | **WON** — sale closed |
| 4 | Calificado | Qualified |
| 5 | Potencial | High intent |
| 6 | Promesa | Verbally committed |
| 7 | Perdido | **LOST** |

Open / active states: 1, 4, 5, 6.
Closed states: 3 (won), 7 (lost), 2 (disqualified).

### `adm.Tipo` — multiple categories share this table, distinguished by `Categoria`
Relevant rows:
| Id | Nombre | Categoria |
|---|---|---|
| 31 | Tiempo Completo | TipoJornada |
| 32 | Tiempo Parcial | TipoJornada |
| 13 | Cancelado | EstadoProducto |
| 14 | Postergado | EstadoProducto |
| 15 | Finalizado | EstadoProducto |
| 16 | No llamar nuevos | EstadoProducto |
| 17 | Piloto | EstadoProducto |
| 18 | En curso | EstadoProducto |
| 19 | Preventa | EstadoProducto |
| 20 | En venta | EstadoProducto |
| 21 | Grupo completo | EstadoProducto |

## 9. Soft-delete + active filters quick reference

| Table | Required filter for "active" |
|---|---|
| `adm.Oportunidad` | `Estado = 1` |
| `adm.HistorialEstado` | `Estado = 1` |
| `adm.Personal` | `Estado = 1 AND ISNULL(Cesado, 0) = 0` |
| `adm.Producto` | `Estado = 1` |
| `adm.Persona` | `Estado = 1` |
| `adm.PotencialCliente` | `Estado = 1` |
| `adm.CobranzaPlan` | `Estado = 1` |
| `adm.CobranzaPago` | `Estado = 1` |
| `mdm.Pais` | `Estado = 1` (catalog filter, rarely needed) |

When joining 4+ tables, putting the `Estado = 1` filter as a join predicate (rather than in the outer `WHERE`) keeps the query plan efficient:

```sql
INNER JOIN adm.Producto pr ON pr.Id = op.IdProducto AND pr.Estado = 1
```

## 10. Join graph (the path you'll travel most)

```
                  ┌─────────────────────┐
                  │ adm.Personal        │
                  │ (asesor)            │
                  └──────────┬──────────┘
                             │ IdPersonal
                             ▼
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│ adm.Producto │◄────┤ adm.Oportunidad │────►│ adm.HistorialEstado│
│              │ Pr  │  (lead)         │ Op  │ (state changes)  │
└──────────────┘     └────┬──────┬─────┘     └──────────────────┘
                          │      │
              IdPotenc.   │      │ IdPersona (mostly NULL!)
                          ▼      ▼
              ┌──────────────────────┐
              │ adm.PotencialCliente │──IdPersona──► adm.Persona ──IdPais──► mdm.Pais
              └──────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │ adm.CobranzaPlan     │──IdCobranzaPlan──► adm.CobranzaPago
              └──────────────────────┘  (one-to-many)
                IdOportunidad
```

The `IdPersona` arrow from Oportunidad is dashed in practice — almost always NULL. Travel via PotencialCliente.

## 11. `adm.LinkedIn_Lead` — raw LinkedIn lead-gen feed (campaña / FormName)

Staging de los leads que entran por LinkedIn Lead Gen Forms. Es la **única** fuente
con detalle de campaña; `Oportunidad.Origen` sólo dice `Linkedin`. **No hay FK directa
a `Oportunidad`** — se relacionarían por `Email` (fuera de alcance de los scripts).
**No tiene columna `Estado`** (sin soft-delete).

| Column | Type | Notes |
|---|---|---|
| `LeadId` | nvarchar | Id del lead en LinkedIn. |
| `CreatedTime` | nvarchar | Timestamp original (texto). |
| `CreatedDate` | date | Fecha de creación. Usar esta para rangos. |
| `AdId`, `CampaignId`, `AccountId`, `FormId` | bigint | Ids numéricos de LinkedIn. `CampaignId` NO es legible. |
| `FormName` | nvarchar | **Nombre legible de la campaña/formulario.** Ver naming pattern abajo. |
| `TestLead` | bit | 1 = lead de prueba. Excluir con `ISNULL(TestLead,0)=0` para análisis reales. |
| `Nombre`, `Apellidos`, `Email`, `Telefono` | nvarchar | Contacto. |
| `PaisRegion` | nvarchar | País/región declarado en el form. |
| `LeadType` | nvarchar | |
| `Revisado` | bit | |

Tablas hermanas: `adm.LinkedIn_Lead_Correctos` y `adm.LinkedIn_Lead_Fallado` (mismo
esquema, leads procesados OK vs. fallidos en el ingest). Para "todos los leads de
LinkedIn" usar `adm.LinkedIn_Lead`.

### Naming pattern de `FormName`
```
[FOR-] <FORMATO> <TEMA> [NIVEL] [SEGMENTO]
```
MAYÚSCULAS, pegado, sin separadores. Ejemplos: `PEPCONTROLFIN`, `CEPRRHH40`,
`PAEGERFINCORP4.0`, `PAEGEREXOLEAN40-GLOBAL`, `FOR-PAEGERMTTO`.

- **FORMATO** (prefijo de 3 letras) = los mismos códigos de producto de §5:
  `PAE`/`CEP`/`PEP`/`PAD`. Estos 4 cubren **>94%** de los leads.
- **TEMA** = abreviatura del curso/área pegada (`GER`, `MTTO`, `FIN`, `RRHH`,
  `POWERBI`, `KEY`…), a veces varias concatenadas.
- **NIVEL** (opcional) = sufijo `40` / `4.0` (industria 4.0).
- **SEGMENTO** (opcional) = sufijo con guion: `-GLOBAL`, `-MIN`, `POR`, `FABRIC`.
- **`FOR-`** = variante "formulario" del mismo código (`FOR-PAEGERMTTO` ≡ `PAEGERMTTO`);
  normalizar quitando el prefijo para no duplicar campañas.
- **Cola larga ad-hoc** (no sigue el patrón): `WOMANLEAD`, `PUENTES DE PAPEL`,
  `HABISITE2026`, `TituLab`, `BECA`, `DOCCOMERCIAL`… — filtrarlas pidiendo
  `FORMATO ∈ {PAE,CEP,PEP,PAD}` si se quiere sólo el catálogo estructurado.

`linkedin_campanas.py` parsea esto en columnas; `conversion_por_origen.py` compara la
TC entre canales.

## 12. Encuestas de módulo (`adm.Encuesta*Respuestas`) — NPS

Tres encuestas por módulo: `adm.EncuestaInicialRespuestas`, `EncuestaIntermediaRespuestas`,
`EncuestaFinalRespuestas`. La **final** es la que trae el NPS. Cada fila = 1 respuesta de 1 alumno
a 1 módulo. **`Estado tinyint`** (1 = activa) — sí tiene soft-delete. Es **data en vivo** (entran
respuestas nuevas a diario; `FechaCreacion` llega hasta hoy).

`adm.EncuestaFinalRespuestas` (columnas clave):
| Column | Type | Notes |
|---|---|---|
| `Id` | int PK | |
| `IdModulo` | int FK | → `adm.Modulo.Id`. **No hay FK a Producto**; el curso se alcanza vía estructura curricular (abajo). |
| `Programa` | nvarchar(255) | Texto libre ≈ nombre del **módulo** (no del curso padre). No sirve para desambiguar curso. |
| `RecomendacionEscala` | tinyint | **0-10. Ésta es la pregunta NPS** ("¿qué tan probable es que recomiendes…?"). |
| `RecomendacionEscala` buckets | | Promotores 9-10 · Pasivos 7-8 · Detractores 0-6. **NPS = %Prom − %Det** (−100…+100). |
| `DesempenoProfesor` | tinyint | Escala aparte (no NPS). |
| `Nombres`, `OpinionDocente`, `ContenidoTematico`, `Testimonio`, … | | Campos abiertos/categóricos de la encuesta. |
| `Estado` | tinyint | 1 = activa. |

### Cadena módulo → curso → desarrollador
No hay FK directa módulo↔producto. El camino:
```
EncuestaFinalRespuestas.IdModulo
  → adm.EstructuraCurricularModulo.IdModulo → .IdEstructuraCurricular
  → adm.EstructuraCurricular.Id → .IdProducto
  → adm.Producto.Id → .PersonalCreacion   (= desarrollador / encargado)
  → adm.Personal.Id (nombre)
```
`adm.EstructuraCurricular` (Id, **IdProducto**, Nombre, Estado) es la malla de un producto;
`adm.EstructuraCurricularModulo` (IdEstructuraCurricular, IdModulo, Orden, Estado) es el puente
N:N módulo↔malla. **Filtrar `Estado=1` en las tres.**

**Gotcha many-to-many:** un módulo puede reaparecer en varios productos (cohortes May/Jun,
variantes), así que el JOIN directo **infla las respuestas** (403 → 1088 en la prueba). PERO a
nivel **desarrollador** la atribución es única: 35/36 módulos encuestados mapean a exactamente 1
desarrollador (los productos que comparten un módulo comparten dueño). **Deduplicar
módulo→desarrollador con `MIN(PersonalCreacion)` ANTES de tocar las respuestas** — así cada
respuesta se cuenta una sola vez. Módulos con producto de `PersonalCreacion` NULL o huérfano
(no existe en `adm.Personal`) → etiqueta "(sin desarrollador)". `nps_encuesta_final.py` lo hace.
