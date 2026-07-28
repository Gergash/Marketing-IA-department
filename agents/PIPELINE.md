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
ContentStrategistAgent          ← lineal (LLM o stub; doctrina inbound inyectada)
  │
  ▼
┌─────────────────────────────┐
│ LangGraph: CopyQAState      │
│   copywriter → qa           │  ← copywriter también lleva inbound
│        ▲         │          │
│        └─ revise ┘          │
│   (hasta max_attempts)       │
└─────────────────────────────┘
  │
  ├─ feed / story ───────────► DesignerAgent        ← lineal (imagen)
  │
  ├─ content_format = reel ──► VideoScriptAgent (inbound) → VideoDesignerAgent
  │
  └─ user_clip_reel ─────────► ClipReelDesigner     ← Drive → Whisper → Shotstack
  │
  ▼
HITL (Aprobar / Rechazar / Solicitar cambios → POST /runs/{id}/revise)
  │  social_account_id del run → token+account_id de esa cuenta (multi-cuenta)
  ▼
PublisherAgent (si QA aprobó) ← lineal (Go sidecar Meta/LinkedIn)
```

Doctrina: `knowledge/inbound_marketing.py` → addendum en Strategist, Copywriter y VideoScriptAgent
(pirámide Entretener → Información → Conexión; `publico_objetivo` del brief).

## Módulos lineales

| Módulo | Rol | Entrada principal | Salida |
|--------|-----|-------------------|--------|
| `strategist.py` | Estrategia de contenido (inbound) | `BriefInput` | `StrategyOutput` |
| `copywriter.py` | Redacción (y revisiones con feedback QA; inbound) | `StrategyOutput`, opcional `qa_feedback` | `CopyOutput` |
| `designer.py` | Imagen: Flux, foto usuario (overlay/img2img) o mock | `BriefInput`, `CopyOutput`, `StrategyOutput` | `DesignOutput` |
| `video_script.py` | Guion reel 3-5 escenas (inbound) | `BriefInput`, `CopyOutput`, `StrategyOutput` | guion escenas |
| `video_designer.py` | Escenas fal + voz + Shotstack (`fal.media` o publicize) | brief, copy, strategy, guion | `VideoDesignOutput` |
| `clip_reel_designer.py` | Reel desde clips Drive | brief, `drive_folder_id` | `VideoDesignOutput` |
| `publisher.py` | Publicación (mock o proveedor real) | plataforma, copy, diseño | `PublishOutput` |
| `quality.py` | Reglas de compliance / tono | texto, `tono_marca` | `QualityReview` |
| `knowledge/inbound_marketing.py` | Doctrina inbound + pirámide redes | — | addendum `_SYSTEM` |

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

## Rama Reels (`content_format="reel"`)

- Tras copy/QA, `MarketingPipeline` delega a `VideoScriptAgent` + `VideoDesignerAgent` en lugar de `DesignerAgent`.
- Render async vía Celery cola `video_render` (no usar `/runs/sync`).
- Con fal.ai, fondos/voz se pasan a Shotstack como URLs `fal.media`; `PUBLIC_IMAGE_BASE_URL` (ngrok) sigue siendo necesario para Meta y assets locales.
- `result["design"]` incluye `video_url` (reels) o `image_url` (feed/story); misma clave `design` en ambos casos.
- Al aprobar, publica a la cuenta fijada en `social_account_id` (multi-cuenta).

## Rama clips usuario (`content_format="user_clip_reel"`)

- Async-only; requiere `drive_folder_id`. Orquestación en `ClipReelDesigner` (Drive → Whisper → hook-scored → captions → wan-effects opcional → Shotstack).
- HITL: Aprobar / Rechazar / **Solicitar cambios** (`POST /runs/{id}/revise` regenera con notas y vuelve a `pending_approval`; nunca publica).
- Publicación: `run.social_account_id` elige la cuenta Meta/LinkedIn destino (`GET /api/auth/accounts`); NULL = cuenta activa más reciente del provider.

## Cuándo ampliar LangGraph

Valor añadido probable:

- Bucles adicionales (p. ej. estratega ↔ stakeholder simulado).
- Ramas condicionales por canal (LinkedIn vs TikTok) con estado compartido pesado.
- Recuperación multi-paso con políticas (backoff, escalado a humano).

Mantener en Python lineal:

- Pasos “una sola vez” sin re-entrada.
- Transformaciones puras cortas (mapeo de DTO, enriquecimiento simple).
