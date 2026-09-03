# Manual de Staging — Marketing DEPA IA

> **Versión:** 2026-09-03  
> **Autor:** PowerUps Ecosistema  
> Cubre: levantar staging en local, estrategia multi-entorno y deploy a VPS sin conflictos de URLs.

---

## Tabla de contenido

1. [Cómo funciona la separación de entornos](#1-cómo-funciona-la-separación-de-entornos)
2. [Requisitos](#2-requisitos)
3. [Levantar staging local — opción A (SQLite, sin Docker)](#3-opción-a--sqlite-sin-docker)
4. [Levantar staging local — opción B (PostgreSQL con Docker)](#4-opción-b--postgresql-con-docker)
5. [Staging con ngrok (webhook Bold + OAuth)](#5-staging-con-ngrok)
6. [Arquitectura de URLs — por qué no hay conflictos](#6-arquitectura-de-urls--por-qué-no-hay-conflictos)
7. [Deploy a producción (VPS Hostinger)](#7-deploy-a-producción-vps-hostinger)
8. [Flujo Git recomendado](#8-flujo-git-recomendado)
9. [Referencia de variables de entorno](#9-referencia-de-variables-de-entorno)
10. [FAQ y errores comunes](#10-faq-y-errores-comunes)

---

## 1. Cómo funciona la separación de entornos

El proyecto usa **tres archivos `.env` distintos**, ninguno se sube al repositorio (todos están en `.gitignore`):

```
.env                    ← desarrollo local (tu máquina)
.env.production         ← VPS Hostinger (solo existe en el servidor)
.env.staging.local      ← alias de referencia (no se usa directamente)
```

El código fuente **no contiene ninguna URL hardcodeada** de ngrok, localhost ni del dominio de producción. Las URLs llegan siempre desde variables de entorno:

| Variable | Local | Producción VPS |
|----------|-------|----------------|
| `DATABASE_URL` | `sqlite:///./marketing_staging.db` o `postgresql://localhost:5433/…` | `postgresql://postgres:5432/…` (Docker interno) |
| `PUBLIC_IMAGE_BASE_URL` | `http://localhost:8000` | `https://marketing.powerupsecosistem.online` |
| `STAGING_SUCCESS_REDIRECT_URL` | `http://localhost:5173/app?paid=1` | `https://marketing.powerupsecosistem.online/app?paid=1` |
| `META_REDIRECT_URI` etc. | `http://localhost:8000/api/auth/callback/meta` | `https://marketing.powerupsecosistem.online/api/auth/callback/meta` |

El **frontend** (Vite) siempre hace peticiones a rutas relativas `/api/*`. En desarrollo, Vite las proxea a `http://127.0.0.1:8000`. En producción, Caddy hace el mismo proxy hacia el contenedor `api:8000`. **El frontend compilado no contiene ninguna URL de backend.**

---

## 2. Requisitos

| Herramienta | Versión mínima | Para qué |
|-------------|---------------|----------|
| Python | 3.10+ | API Gateway |
| Node.js | 18+ | Frontend Vite |
| Docker Desktop | cualquier | PostgreSQL + Redis (Opción B) |
| ngrok | cualquier | Webhook Bold en local (opcional) |
| Git | cualquier | Control de versiones |

Instalar dependencias Python una sola vez:

```bash
cd "Marketing DEPA IA"
pip install -r requirements.txt
# PyJWT y pydantic[email] ya están en requirements.txt
```

---

## 3. Opción A — SQLite (sin Docker)

**La más rápida. Ideal para revisar la UI del staging sin levantar Docker.**  
No tiene Redis → los jobs Celery (videos, async) no funcionan, pero el flujo landing→login→Bold→créditos funciona completo.

### 3.1 Configurar `.env`

En la raíz del proyecto (`Marketing DEPA IA/.env`), asegúrate de tener:

```dotenv
# Base de datos — SQLite local, sin Docker
DATABASE_URL=sqlite:///./marketing_staging.db
# DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/marketing_mvp  ← comentar

# Staging SaaS
STAGING_SAAS_ENABLED=true
JWT_SECRET=staging-dev-secret-cambia-en-prod
JWT_TTL_MINUTES=10080
BOLD_API_KEY=                    # dejar vacío para ver UI sin pago
BOLD_INTEGRITY_SECRET=
BOLD_WEBHOOK_SECRET=
PACK_AMOUNT_COP=99000
CREDITS_PER_PACK=100
STAGING_SUCCESS_REDIRECT_URL=http://localhost:5173/app?paid=1
```

### 3.2 Configurar `frontend/.env.local`

```dotenv
VITE_STAGING_SAAS=true
```

### 3.3 Inicializar la base de datos

```bash
cd "Marketing DEPA IA"
python -c "
from gateway.app.db.session import Base, engine
from gateway.app.models.entities import *
from gateway.app.db.schema_patches import apply_lightweight_migrations
Base.metadata.create_all(bind=engine)
apply_lightweight_migrations(engine)
print('BD lista')
"
```

### 3.4 Levantar el backend

```bash
# Terminal 1 — API Gateway
cd "Marketing DEPA IA"
python -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Verificar que arrancó:
```bash
curl http://localhost:8000/api/auth/me
# → {"email":"","tenant_id":"demo-tenant","staging_enabled":true,...}
```

### 3.5 Levantar el frontend

```bash
# Terminal 2 — Frontend Vite
cd "Marketing DEPA IA/frontend"
npm run dev
```

### 3.6 Ver en el navegador

| URL | Pantalla |
|-----|----------|
| `http://localhost:5173/` | Landing del departamento |
| `http://localhost:5173/login` | Registro / Login |
| `http://localhost:5173/app` | Estudio de marketing |

---

## 4. Opción B — PostgreSQL con Docker

**Recomendada para probar el pipeline completo** (generación de imágenes, Celery, videos).

### 4.1 Verificar que Docker Desktop está activo

```bash
docker info
# Debe mostrar "Server:" sin errores
```

Si Docker no está corriendo: abre **Docker Desktop** desde el menú de Windows y espera a que aparezca el ícono en verde en la barra de tareas.

### 4.2 Levantar Postgres + Redis

```bash
cd "Marketing DEPA IA"
docker compose -f infra/docker-compose.yml up -d
# Verifica:
docker compose -f infra/docker-compose.yml ps
```

Debe mostrar `postgres` y `redis` en estado `healthy`.

### 4.3 Configurar `.env` con PostgreSQL

Edita `.env` y cambia la línea de base de datos:

```dotenv
# Comentar SQLite:
# DATABASE_URL=sqlite:///./marketing_staging.db

# Activar PostgreSQL:
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/marketing_mvp
```

Mantén el resto de variables de staging igual que en la Opción A.

### 4.4 Aplicar migraciones

```bash
cd "Marketing DEPA IA"
alembic upgrade head
# Debe mostrar "Running upgrade ... -> 0008, staging saas users credits"
```

### 4.5 Levantar todos los servicios

```bash
# Terminal 1 — API Gateway
python -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — Worker Celery (generación async + videos)
python -m celery -A workers.celery_app.celery_app worker -l info -Q celery -c 2

# Terminal 3 — Worker de video (opcional, solo para reels)
python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render -c 1

# Terminal 4 — Frontend
cd frontend
npm run dev
```

### 4.6 Opcional: Go publisher (para publicar en Meta/IG)

```bash
# Terminal 5 — Go sidecar
cd microservices/social-publisher-go
go run ./cmd/server
# Corre en :8088
```

---

## 5. Staging con ngrok

Necesario para:
- Recibir el **webhook Bold** cuando alguien paga
- Probar **OAuth callbacks** de Meta, X, LinkedIn en local

### 5.1 Instalar ngrok

```bash
# Windows — Chocolatey
choco install ngrok

# O descargar desde https://ngrok.com/download
```

### 5.2 Exponer el backend

```bash
# En una terminal aparte (con uvicorn ya corriendo en :8000)
ngrok http 8000
```

ngrok te da una URL como:
```
https://abc123.ngrok-free.app
```

### 5.3 Actualizar `.env` con la URL ngrok (SOLO en local, no se commitea)

```dotenv
# Reemplaza SOLO estas variables con la URL ngrok actual:
PUBLIC_IMAGE_BASE_URL=https://abc123.ngrok-free.app
STAGING_SUCCESS_REDIRECT_URL=https://abc123.ngrok-free.app/app?paid=1

# OAuth callbacks (si vas a probar conectar redes sociales):
META_REDIRECT_URI=https://abc123.ngrok-free.app/api/auth/callback/meta
LINKEDIN_REDIRECT_URI=https://abc123.ngrok-free.app/api/auth/callback/linkedin
X_REDIRECT_URI=https://abc123.ngrok-free.app/api/auth/callback/x
```

Reinicia uvicorn después de cambiar `.env`.

### 5.4 Configurar webhook Bold

En el panel Bold → **Configuración → Notificaciones**:
```
URL: https://abc123.ngrok-free.app/api/billing/bold-webhook
```

Y pon las llaves Bold en `.env`:
```dotenv
BOLD_API_KEY=tu_llave_identidad
BOLD_INTEGRITY_SECRET=tu_llave_secreta
BOLD_WEBHOOK_SECRET=tu_llave_secreta   # misma que BOLD_INTEGRITY_SECRET
```

### ⚠️ Importante: ngrok cambia la URL cada vez que lo reinicias

**Cada vez que reinicies ngrok**, la URL cambia. Debes:
1. Actualizar las 3-4 variables en `.env`
2. Actualizar el webhook en el panel Bold
3. Reiniciar uvicorn

Esto **no afecta el repositorio** porque `.env` nunca se sube.

---

## 6. Arquitectura de URLs — por qué no hay conflictos

```
┌─────────────────────────────────────────────────────────────────┐
│  CÓDIGO FUENTE (git)                                            │
│                                                                 │
│  frontend/src/auth.js:                                          │
│    fetch(`${apiBase()}/api/auth/register`)  ← ruta relativa    │
│                                                                 │
│  vite.config.js:                                                │
│    proxy: { "/api": "http://127.0.0.1:8000" }  ← hardcoded OK │
│    (solo aplica en dev; en prod Caddy hace el proxy)            │
│                                                                 │
│  docker-compose.prod.yml:                                       │
│    PUBLIC_IMAGE_BASE_URL: https://${DOMAIN}  ← usa variable    │
│    META_REDIRECT_URI: https://${DOMAIN}/api/auth/callback/meta  │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         │ git push                     │ NO existe en git
         ▼                              ▼
┌─────────────────┐          ┌─────────────────────────┐
│  .env (local)   │          │  .env.production (VPS)  │
│                 │          │                         │
│ DATABASE_URL=   │          │ DATABASE_URL=           │
│  sqlite://…     │          │  postgresql://postgres  │
│                 │          │  :5432/marketing_mvp    │
│ PUBLIC_IMAGE_   │          │                         │
│ BASE_URL=       │          │ DOMAIN=marketing.       │
│  localhost:8000 │          │  powerupsecosistem.     │
│  (o ngrok URL)  │          │  online                 │
└─────────────────┘          └─────────────────────────┘
```

**Regla de oro:** Todo lo que cambia entre entornos vive en `.env`. El código fuente nunca tiene URLs de dominio.

---

## 7. Deploy a producción (VPS Hostinger)

Cuando el staging esté validado:

### 7.1 Hacer push del código

```bash
# En tu máquina local
git add -A
git commit -m "feat: staging SaaS landing Bold credits"
git push origin main        # rama de desarrollo
# Cuando esté aprobado:
git checkout master
git merge main
git push origin master      # rama de producción (VPS)
```

### 7.2 En la VPS

```bash
ssh insightflow@2.25.107.229
cd ~/apps/marketing-depa-ia

# Traer cambios
git pull origin master

# Editar .env.production (SOLO en la VPS, nunca en local)
nano .env.production
# Añadir las variables de staging SaaS:
#   STAGING_SAAS_ENABLED=true
#   JWT_SECRET=<secreto largo aleatorio>
#   BOLD_API_KEY=...
#   BOLD_INTEGRITY_SECRET=...
#   BOLD_WEBHOOK_SECRET=...
#   PACK_AMOUNT_COP=99000
#   CREDITS_PER_PACK=100
#   STAGING_SUCCESS_REDIRECT_URL=https://marketing.powerupsecosistem.online/app?paid=1

# Rebuild y restart
docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d --build

# Verificar
docker compose -f infra/docker-compose.prod.yml ps
curl https://marketing.powerupsecosistem.online/api/auth/me
```

### 7.3 La migración se aplica automáticamente

El `docker-compose.prod.yml` ya tiene en el comando de la API:
```yaml
command:
  - sh -c "python -m alembic upgrade head && uvicorn ..."
```

Las tablas `app_users`, `credit_wallets` y `payment_records` se crean solas al reiniciar.

### 7.4 Webhook Bold en producción

En el panel Bold actualizar la URL a:
```
https://marketing.powerupsecosistem.online/api/billing/bold-webhook
```

---

## 8. Flujo Git recomendado

```
main (desarrollo)  ──── staging local ─────────────────────────────►
                              │                                      
                              │ valida OK                            
                              ▼                                      
master (producción) ─── git merge main ─── git push ─── pull VPS ──►
```

**Archivos que NUNCA van al repo:**
- `.env` (local)
- `.env.production` (VPS)
- `frontend/.env.local`
- `*.db`, `*.db-shm`, `*.db-wal` (SQLite)
- `static/images/*.png`, `static/videos/`

Todos están en `.gitignore`. Puedes verificar con:
```bash
git status --ignored
```

---

## 9. Referencia de variables de entorno

### Variables de staging (nuevas)

| Variable | Obligatoria | Descripción |
|----------|------------|-------------|
| `STAGING_SAAS_ENABLED` | Sí | `true` activa landing/login/Bold/créditos |
| `JWT_SECRET` | Sí | Secreto para firmar tokens de sesión. Mín. 32 chars en prod |
| `JWT_TTL_MINUTES` | No | Duración del token (default: 10080 = 7 días) |
| `BOLD_API_KEY` | Para pago | Llave de identidad (panel Bold → Integraciones → Botón de pagos) |
| `BOLD_INTEGRITY_SECRET` | Para pago | Llave secreta para firmar el hash del botón |
| `BOLD_WEBHOOK_SECRET` | Para pago | Misma llave que `BOLD_INTEGRITY_SECRET` |
| `PACK_AMOUNT_COP` | No | Monto del paquete en COP (default: 99000) |
| `CREDITS_PER_PACK` | No | Créditos que se acreditan por pago (default: 100) |
| `STAGING_SUCCESS_REDIRECT_URL` | No | URL de redirección tras pago Bold |

### Costos de créditos por publicación

| Tipo de pieza | Créditos |
|---------------|----------|
| Imagen estática | 1 |
| Imagen generada con IA | 2 |
| Foto propia con overlay/diseño | 2 |
| Video con subtítulos | 5 |
| Reel / clip con IA | 8 |

### Endpoints nuevos del backend

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/auth/register` | Registro (email único, contraseña ≥8 chars) |
| `POST` | `/api/auth/login` | Login → devuelve JWT |
| `GET` | `/api/auth/me` | Perfil + saldo de créditos (requiere JWT) |
| `GET` | `/api/billing/credits` | Saldo y tabla de costos |
| `GET` | `/api/billing/bold-checkout` | Firma del botón Bold (requiere JWT) |
| `POST` | `/api/billing/bold-webhook` | Webhook de confirmación de pago Bold |

---

## 10. FAQ y errores comunes

### ❌ `ModuleNotFoundError: No module named 'oauthlib'`
```bash
pip install oauthlib PyJWT "pydantic[email]"
```

### ❌ `email-validator is not installed`
```bash
pip install "pydantic[email]"
```

### ❌ Docker no arranca: `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`
Docker Desktop no está iniciado. Abre la app desde el menú de Windows, espera el ícono verde, y vuelve a correr `docker compose up`.

### ❌ `Bold no configurado: faltan BOLD_API_KEY o BOLD_INTEGRITY_SECRET`
Normal si no tienes llaves Bold todavía. El flujo de registro funciona igual; el botón de pago simplemente no renderiza hasta tener las llaves.

### ❌ Ya existe una cuenta con ese correo
El sistema rechaza emails duplicados por diseño. Usa el tab **Login** en vez de **Registro** si ya tienes cuenta.

### ❌ `Créditos insuficientes` al intentar publicar
Necesitas recargar con Bold. En staging local puedes agregar créditos manualmente para testing:
```bash
python -c "
from gateway.app.db.session import SessionLocal
from gateway.app.services.credits_service import add_credits
db = SessionLocal()
add_credits(db, 'TU_TENANT_ID', 500)
print('500 créditos añadidos')
db.close()
"
```
El `tenant_id` lo ves en la respuesta de `/api/auth/me`.

### ❌ ngrok URL cambió y el OAuth ya no funciona
1. Copia la nueva URL de ngrok
2. Actualiza en `.env`: `PUBLIC_IMAGE_BASE_URL`, `META_REDIRECT_URI`, `X_REDIRECT_URI`, etc.
3. Actualiza en el panel de Meta Developers / X Developer Portal la URL de callback
4. Reinicia uvicorn (`Ctrl+C` y vuelves a correr `python -m uvicorn ...`)

### ✅ ¿Cómo verificar que todo está bien?

```bash
# Backend responde
curl http://localhost:8000/api/auth/me

# Registro funciona
curl -s -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@local.com","password":"test1234","full_name":"Test"}' | python -m json.tool

# Frontend sirve
curl -s http://localhost:5173/ | grep "Marketing DEPA IA"
```

---

## Apéndice — Comandos de arranque rápido (copiar y pegar)

### Opción A — SQLite (más rápido)

```bash
# Terminal 1
cd "c:/Users/57317/Desktop/PowerUps/Marketing DEPA IA"
python -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
cd "c:/Users/57317/Desktop/PowerUps/Marketing DEPA IA/frontend"
npm run dev
```

Abre: **http://localhost:5173/**

### Opción B — PostgreSQL con Docker

```bash
# Paso 0: abrir Docker Desktop y esperar ícono verde

# Terminal 1 — Servicios Docker
cd "c:/Users/57317/Desktop/PowerUps/Marketing DEPA IA"
docker compose -f infra/docker-compose.yml up -d

# Cambiar DATABASE_URL en .env a:
# DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/marketing_mvp

# Aplicar migración
alembic upgrade head

# Terminal 2 — API
python -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 3 — Worker (para generación async)
python -m celery -A workers.celery_app.celery_app worker -l info -Q celery -c 2

# Terminal 4 — Frontend
cd frontend && npm run dev
```

### Con ngrok (para Bold + OAuth)

```bash
# Terminal extra
ngrok http 8000
# → copia la URL https://xxxxx.ngrok-free.app
# → actualiza PUBLIC_IMAGE_BASE_URL y STAGING_SUCCESS_REDIRECT_URL en .env
# → reinicia uvicorn
```
