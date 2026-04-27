# Orquestación del pipeline de marketing

## Principio

- **Flujos lineales** (un paso detrás de otro, sin ciclos): implementados como Python modular en `marketing_agents/` y coordinados desde `MarketingPipeline`.
- **Flujos que requieren ciclos, trazabilidad explícita o reintentos guiados** (Copywriter ↔ QA): implementados con **LangGraph** en `graph_copy_qa.py`.

LangGraph no sustituye al pipeline completo: solo encapsula el subgrafo donde tiene sentido el estado compartido y las transiciones condicionales.

## Flujo global (alto nivel)

```text
Brief
  │
  ▼
ContentStrategistAgent          ← lineal (LLM o stub)
  │
  ▼
┌─────────────────────────────┐
│ LangGraph: CopyQAState      │
│   copywriter → qa           │
│        ▲         │          │
│        └─ revise ┘          │
│   (hasta max_attempts)       │
└─────────────────────────────┘
  │
  ▼
DesignerAgent                   ← lineal
  │
  ▼
PublisherAgent (si QA aprobó) ← lineal
```

## Módulos lineales

| Módulo | Rol | Entrada principal | Salida |
|--------|-----|-------------------|--------|
| `strategist.py` | Estrategia de contenido | `BriefInput` | `StrategyOutput` |
| `copywriter.py` | Redacción (y revisiones con feedback QA) | `StrategyOutput`, opcional `qa_feedback` | `CopyOutput` |
| `designer.py` | Imagen / prompt visual | `BriefInput`, `CopyOutput` | `DesignOutput` |
| `publisher.py` | Publicación (mock o proveedor real) | plataforma, copy, diseño | `PublishOutput` |
| `quality.py` | Reglas de compliance / tono | texto, `tono_marca` | `QualityReview` |

## Subgrafo LangGraph (`graph_copy_qa.py`)

### Estado (`CopyQAState`)

- `brief`, `strategy`: contexto fijo del tramo.
- `copy`, `quality`: última versión del borrador y resultado QA.
- `attempt`: número de ronda de copy (sube en cada visita al nodo copywriter).
- `max_attempts`: tope de rondas (se pasa en `invoke`).
- `events`: lista acumulada (reducer `operator.add`) con un dict por paso para **trazabilidad** (nodo, aprobación, motivos, si hubo feedback previo).

### Transiciones

1. Entrada → **copywriter**: primera vez sin feedback; tras QA fallido, con `quality.reasons` como `qa_feedback` al LLM/stub.
2. **qa**: ejecuta `ContentQualityGuard.validate`.
3. Condición:
   - Si `approved` → **END**.
   - Si no aprobado y `attempt < max_attempts` → otra vuelta a **copywriter** (`revise`).
   - Si no aprobado y ya se alcanzó el tope → **END** (se conserva último copy y `quality`; publicación queda bloqueada en `MarketingPipeline` si `approved` es falso).

### Parámetro `MarketingPipeline(max_copy_qa_attempts=3)`

Controla cuántas rondas de copy como máximo se permiten antes de salir del grafo sin aprobación.

## Salida del pipeline

`MarketingPipeline.run` devuelve un dict que incluye:

- `strategy`, `copy`, `design`, `quality`, `publish_result` (como antes).
- **`copy_qa_trace`**: lista ordenada de eventos del grafo (auditoría / debugging / UI futura).

## Cuándo ampliar LangGraph

Valor añadido probable:

- Bucles adicionales (p. ej. estratega ↔ stakeholder simulado).
- Ramas condicionales por canal (LinkedIn vs TikTok) con estado compartido pesado.
- Recuperación multi-paso con políticas (backoff, escalado a humano).

Mantener en Python lineal:

- Pasos “una sola vez” sin re-entrada.
- Transformaciones puras cortas (mapeo de DTO, enriquecimiento simple).
