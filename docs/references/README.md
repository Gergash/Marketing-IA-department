# Referencia: pieza de campaña con manual de marca

Archivo: `brand-campaign-piece-tres-amores.png`

Esta es la **pieza objetivo** que el pipeline genera cuando hay manual de marca activo
(`brand_context` / cues de `brand_scan` + `brand_visual`):

1. **Foto full-bleed** del producto/lugar/atmósfera (sin cards ni collages).
2. **Logo de marca** arriba-centro (extraído del PDF vía `brand_scan`).
3. **Headline expresivo** centrado (script/display — Great Vibes / Playfair en `static/fonts/`).
4. **Una línea de apoyo** corta.
5. **Un CTA** cerca del borde inferior (borde de acento de marca).
6. **Eslogan** opcional al pie.
7. Marco fino y viñeta suave; **paleta** del escaneo/OCR del brand book.

Arquetipo en código: `brand_campaign_piece`  
(`layout_archetypes.py` + overlay en `design_layouts.py`).

Flujo de datos: PDF → `brand_manual` / `ocr_paddle` / `brand_scan` → `BriefInput` → `DesignerAgent`.

Documentación de estado: `estado-actual.txt` (sección Motor visual y marca).
