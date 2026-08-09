# Cómo subir Marketing DEPA IA a NotebookLM

## Qué subir (recomendado)

Sube **un solo archivo** como fuente principal:

`docs/notebooklm/Marketing-DEPA-IA-fuente-completa.md`

Es autocontenido (producto, arquitectura, agentes, marca, API, operación, límites y glosario). NotebookLM responde mejor con pocas fuentes densas y claras.

## Pasos en NotebookLM

1. Abre [NotebookLM](https://notebooklm.google.com) y crea un notebook nuevo (p. ej. “Marketing DEPA IA”).
2. **Añadir fuente** → **Subir** → elige el `.md` anterior.
   - Si NotebookLM pide PDF: abre el `.md` en VS Code / Word / Google Docs → Exportar o Imprimir a PDF, y sube el PDF.
3. Espera a que indexe la fuente.
4. (Opcional) Añade como segunda fuente `estado-actual.txt` de la raíz del repo si quieres más detalle histórico.

## No hace falta subir

- `.env`, claves, tokens, logs de terminales.
- Carpetas `static/uploads`, `node_modules`, venv.
- Documentación fragmentada del resto del repo (ya está consolidada en la fuente completa).

## Preguntas de arranque sugeridas

- Resume el proyecto en 10 viñetas.
- Dibuja el flujo brief → publicación.
- Explica el manual de marca y el arquetipo brand_campaign_piece.
- Lista huecos conocidos (revise, contraste, LLM stub, Meta/ngrok).
- Genera un checklist de arranque del stack en 8 terminales.
- Compara feed vs story vs reel vs user_clip_reel.

## Actualización de esta fuente

Cuando cambie el producto de forma relevante, regenera o edita `Marketing-DEPA-IA-fuente-completa.md` y **vuelve a subir** la fuente en NotebookLM (o reemplázala). La fecha del documento está en la cabecera.
