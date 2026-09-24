# Cómo subir Marketing DEPA IA a NotebookLM

## Qué subir (recomendado)

Sube **un solo archivo** como fuente principal:

`docs/notebooklm/Marketing-DEPA-IA-fuente-completa.md`

Es autocontenido (producto, arquitectura, agentes, marca, API, operación, **OAuth Google Drive / GOOGLE_CLIENT_ID**, límites y glosario). NotebookLM responde mejor con pocas fuentes densas y claras.

Fecha de la fuente: ver cabecera del `.md` (**Actualizado: 2026-09-10** — **no incluye Auth0-only ni panel admin de la noche del 17-sep**).

Para el estado SaaS/Auth0/admin actual, segunda fuente opcional:

- `estado-actual.txt`
- `docs/estado-saas-auth0-2026-09-17.md`

## Pasos en NotebookLM

1. Abre [NotebookLM](https://notebooklm.google.com) y crea un notebook nuevo (p. ej. “Marketing DEPA IA”) o abre el existente.
2. Si ya había una fuente vieja: **elimínala o reemplázala** para que Gemini no mezcle el flujo antiguo de clips (descarga completa) con el cloud actual.
3. **Añadir fuente** → **Subir** → elige el `.md` anterior.
   - Si NotebookLM pide PDF: abre el `.md` en VS Code / Word / Google Docs → Exportar o Imprimir a PDF, y sube el PDF.
4. Espera a que indexe la fuente.
5. (Opcional) Segunda fuente: `estado-actual.txt` (cronología viva) y/o `docs/estado-saas-auth0-2026-09-17.md` (Auth0 + panel admin 17-sep).

## No hace falta subir

- `.env`, claves, tokens, logs de terminales.
- Carpetas `static/uploads`, `node_modules`, venv.
- Documentación fragmentada del resto del repo (ya está consolidada en la fuente completa).

## Pregunta prioritaria (Google Drive)

Cuando la fuente esté indexada, pregunta exactamente:

> Basándote solo en la fuente, dame el paso a paso para obtener y configurar `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` en local, habilitar Drive API, pantalla de consentimiento, test users, conectar desde Integraciones, y qué cambia en producción en `marketing.powerupsecosistem.online`. Incluye la tabla de fallos frecuentes (`redirect_uri_mismatch`, sin refresh_token, etc.).

El detalle vive en la sección **«16. Cómo conectar Google Drive (GOOGLE_CLIENT_ID) — paso a paso»** del documento fuente.

## Otras preguntas de arranque

- Resume el proyecto en 10 viñetas.
- Dibuja el flujo brief → (`pending_takes` si clips) → `pending_approval` → publicación.
- Explica el manual de marca y el arquetipo brand_campaign_piece.
- Lista huecos conocidos (revise, LLM stub, Meta/ngrok, TikTok App Review).
- Genera un checklist de arranque del stack (incl. worker `video_render` + ffmpeg).
- Compara feed vs story vs reel vs user_clip_reel (cloud).

## Actualización de esta fuente

Cuando cambie el producto de forma relevante, edita `Marketing-DEPA-IA-fuente-completa.md` y **vuelve a subir / reemplazar** la fuente en NotebookLM. No dejes dos versiones solapadas del mismo doc.
