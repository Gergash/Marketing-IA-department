# Prueba de Fuego del Scheduler

Valida que **APScheduler** dispara campañas de forma autónoma, genera contenido y deja el run en **`pending_approval`** para revisión humana — **sin auto-publicar**.

> Alcance: scheduler + pipeline de generación. No requiere ComfyUI/Flux ni GPU. Usa `IMAGE_PROVIDER=mock` y LLM stub si no hay API keys.

---

## Arquitectura (resumen)

| Componente | Rol en la prueba |
|---|---|
| **uvicorn** (`gateway.app.main`) | Arranca APScheduler en el mismo proceso (`start_scheduler()` en startup) |
| **APScheduler** | Job `campaign-heartbeat` cada 5 min sincroniza BD → jobs cron |
| **Jobs `campaign-{id}`** | Disparan `_fire_campaign()` según `cron_expr` en `campaign_schedules` |
| **`_fire_campaign`** | Crea `Brief` + `AgentRun` (`run_mode=scheduled`) → `execute_pipeline(publish=False, requires_approval=True)` |
| **Pipeline** | Strategist → Copy/QA → Designer (mock image) → **NO publica** |
| **Estado final** | `agent_runs.status = pending_approval` |

Celery/Redis **no son obligatorios** para esta prueba: el scheduler ejecuta el pipeline **síncrono** en el proceso API.

---

## Prerrequisitos

1. Python 3.10 + venv con `pip install -r requirements.txt`
2. `.env` con generación sin GPU:

```env
IMAGE_PROVIDER=mock
SOCIAL_PROVIDER=mock
# Opcional: sin API keys de LLM → stub determinístico
```

3. Base de datos:
   - **SQLite (rápido):** `DATABASE_URL=sqlite:///./marketing.db` (default)
   - **PostgreSQL:** `docker compose -f infra/docker-compose.yml up -d` + `alembic upgrade head`

---

## Opción A — Script seed (recomendado)

Con **uvicorn ya corriendo** en otra terminal:

```bash
# Terminal 1 — API (scheduler incluido)
uvicorn gateway.app.main:app --reload --port 8000

# Terminal 2 — seed + disparo inmediato
python scripts/seed_fire_test_campaign.py --fire-now
```

Sin `--fire-now`, solo inserta/actualiza la campaña con cron `* * * * *` (cada minuto UTC). Espera hasta 1 minuto para el disparo automático.

---

## Opción B — API REST

```bash
# 1. Crear campaña (el scheduler se sincroniza al instante)
curl -s -X POST http://localhost:8000/api/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "tema": "Prueba de Fuego Scheduler",
    "red_social": "instagram",
    "objetivo": "branding",
    "cron_expr": "* * * * *"
  }'

# 2a. Disparo manual (sin esperar al cron)
curl -s -X POST http://localhost:8000/api/campaigns/1/fire

# 2b. O esperar al cron (máx. 1 min si cron = * * * * *)
```

Si `API_KEY` está configurado, añade: `-H "Authorization: Bearer <API_KEY>"`

---

## Opción C — SQL directo (PostgreSQL)

```sql
INSERT INTO campaign_schedules (tenant_id, tema, red_social, objetivo, cron_expr, enabled, created_at)
VALUES ('demo-tenant', 'Prueba de Fuego Scheduler', 'instagram', 'branding', '* * * * *', true, NOW());
```

Reinicia uvicorn **o** espera el heartbeat de sincronización (5 min). Mejor: usa Opción A o B para sync inmediato.

---

## Verificación

### 1. Logs del gateway

Busca:

```
scheduler.job_added campaign_id=...
scheduler.campaign_fired campaign_id=... run_id=...
pipeline.pending_approval run_id=...
```

### 2. Base de datos

**SQLite:**

```bash
sqlite3 marketing.db "SELECT id, status, run_mode, created_at FROM agent_runs ORDER BY id DESC LIMIT 5;"
```

**PostgreSQL:**

```sql
SELECT id, status, run_mode, tenant_id, created_at
FROM agent_runs
WHERE run_mode = 'scheduled'
ORDER BY id DESC
LIMIT 5;
```

Esperado: `status = 'pending_approval'`, `run_mode = 'scheduled'`.

Confirmar que **no** hay publicación:

```sql
SELECT COUNT(*) FROM publications;
-- Debe ser 0 para runs aún no aprobados
```

### 3. API

```bash
curl -s http://localhost:8000/api/runs | python -m json.tool
```

### 4. Dashboard (frontend)

```bash
cd frontend && npm run dev
```

Abre http://localhost:5173 — el run debe mostrar botones **Aprobar / Rechazar** (estado `pending_approval`).

---

## Timeline esperado

| Evento | Cuándo |
|---|---|
| `POST /api/campaigns` o seed script | Inmediato |
| Sync APScheduler | Inmediato (API) o ≤ 5 min (solo SQL manual) |
| Disparo cron `* * * * *` | Próximo minuto en punto (UTC) |
| `POST /campaigns/{id}/fire` | Inmediato (~10–30 s con mock) |
| Run en `pending_approval` | Al terminar el pipeline |
| Publicación | **Solo** tras `POST /api/runs/{id}/approve` (humano) |

---

## Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| No aparece job en logs | uvicorn no corriendo | Levantar API; el scheduler no es proceso separado |
| Campaña creada pero no dispara | Sync pendiente | `POST /campaigns` o `python scripts/seed_fire_test_campaign.py` |
| Run en `failed` | LLM/imagen real sin servicio | `IMAGE_PROVIDER=mock` en `.env`, reiniciar uvicorn |
| Cron inválido | Expresión mal formada | 5 campos: `min hour day month dow` |
| Dos runs por minuto | Cron `* * * * *` + múltiples reinicios | Normal en dev; desactiva campaña tras validar |

---

## Tests automatizados

```bash
pytest tests/test_scheduler.py -v
```

Valida que el flujo programado termina en `pending_approval` sin registros en `publications`.
