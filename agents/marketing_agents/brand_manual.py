"""Manual de marca (PDF): almacenamiento por tenant, extracción de texto e inyección en prompts."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"
_BRAND_ROOT = _STATIC_ROOT / "uploads" / "brand"

ALLOWED_BRAND_MIME = frozenset({"application/pdf"})
MAX_BRAND_BYTES = 20 * 1024 * 1024  # 20 MB
_MAX_PROMPT_CHARS = 6000


def brand_dir(tenant_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", (tenant_id or "default").strip()) or "default"
    path = _BRAND_ROOT / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_url_for_brand(tenant_id: str, filename: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", (tenant_id or "default").strip()) or "default"
    return f"http://localhost:8000/static/uploads/brand/{safe}/{filename}"


def _normalize_text(joined: str) -> str:
    joined = re.sub(r"[ \t]+\n", "\n", joined)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def extract_pdf_text_pypdf(raw: bytes, *, max_pages: int = 40) -> str:
    """Extrae texto embebido del PDF (sin OCR)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Falta dependencia pypdf. Instala con: pip install pypdf"
        ) from exc

    import io

    reader = PdfReader(io.BytesIO(raw))
    chunks: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if text:
            chunks.append(text)
    return _normalize_text("\n\n".join(chunks))


def extract_pdf_text(raw: bytes, *, max_pages: int | None = None) -> tuple[str, str]:
    """Extrae texto: pypdf primero; si es insuficiente y OCR_PROVIDER=paddle, PaddleOCR.

    Returns:
        (texto, método) donde método es ``pypdf`` | ``paddleocr`` | ``pypdf+paddleocr``.
    """
    from gateway.app.core.settings import get_settings

    s = get_settings()
    pages = max_pages if max_pages is not None else int(s.ocr_max_pages or 40)
    min_chars = int(s.ocr_min_text_chars or 40)

    text = extract_pdf_text_pypdf(raw, max_pages=pages)
    method = "pypdf"
    if len(text) >= min_chars:
        logger.info("brand_manual.extract_ok", method=method, chars=len(text))
        return text, method

    provider = (s.ocr_provider or "none").strip().lower()
    if provider != "paddle":
        logger.warning(
            "brand_manual.extract_short",
            chars=len(text),
            ocr_provider=provider,
            hint="Activa OCR_PROVIDER=paddle para PDFs escaneados",
        )
        return text, method

    logger.info(
        "brand_manual.ocr_fallback",
        pypdf_chars=len(text),
        min_chars=min_chars,
        lang=s.ocr_lang,
        use_gpu=s.ocr_use_gpu,
    )
    from .ocr_paddle import ocr_pdf_bytes

    ocr_text = ocr_pdf_bytes(
        raw,
        lang=(s.ocr_lang or "es").strip() or "es",
        use_gpu=bool(s.ocr_use_gpu),
        max_pages=pages,
        dpi=int(s.ocr_dpi or 200),
    )
    ocr_text = _normalize_text(ocr_text)
    if len(ocr_text) > len(text):
        method = "paddleocr" if len(text) < 10 else "pypdf+paddleocr"
        logger.info("brand_manual.extract_ok", method=method, chars=len(ocr_text))
        return ocr_text, method

    logger.warning("brand_manual.ocr_no_gain", pypdf_chars=len(text), ocr_chars=len(ocr_text))
    return text, method


def save_brand_manual(
    tenant_id: str,
    raw: bytes,
    *,
    original_filename: str,
) -> dict:
    """Guarda PDF + texto + escaneo visual (paleta/logos) y lo marca activo del tenant."""
    from .brand_scan import scan_brand_pdf

    text, method = extract_pdf_text(raw)
    dest_dir = brand_dir(tenant_id)
    stem = uuid.uuid4().hex

    # Escaneo minucioso: logos, paleta, tipografías y disposiciones
    scan = scan_brand_pdf(
        raw,
        dest_dir=dest_dir,
        tenant_id=tenant_id,
        stem=stem,
        url_builder=local_url_for_brand,
        text=text,
    )

    if len(text) < 40 and not scan.palette_hex and not scan.logo_filenames:
        raise RuntimeError(
            "No se pudo extraer texto útil ni paleta/logos del PDF. "
            "Si es un escaneo, instala PaddleOCR "
            "(pip install paddlepaddle paddleocr pymupdf) y reinicia el gateway "
            "con OCR_PROVIDER=paddle."
        )

    # Si el OCR/texto es corto pero el escaneo visual sí encontró identidad,
    # sintetiza un bloque usable por los agentes.
    if len(text) < 80 and (
        scan.palette_hex or scan.logo_filenames or scan.font_names or scan.layout_hints
    ):
        bits = ["Identidad visual detectada por escaneo del manual."]
        if scan.palette_hex:
            bits.append(f"Paleta de colores: {', '.join(scan.palette_hex)}.")
        if scan.color_roles:
            roles = ", ".join(f"{k}={v}" for k, v in scan.color_roles.items())
            bits.append(f"Roles de color: {roles}.")
        if scan.font_names:
            bits.append(f"Tipografías: {', '.join(scan.font_names)}.")
        if scan.logo_filenames:
            bits.append(f"Logos detectados: {len(scan.logo_filenames)}.")
        if scan.logo_placements:
            bits.append(f"Ubicación habitual del logo: {', '.join(scan.logo_placements)}.")
        if scan.layout_hints:
            bits.append(f"Disposiciones: {'; '.join(scan.layout_hints)}.")
        if scan.suggested_archetype:
            bits.append(f"Layout sugerido: {scan.suggested_archetype}.")
        text = _normalize_text(" ".join(bits) + "\n\n" + text)
        method = f"{method}+visual_scan" if method else "visual_scan"

    pdf_name = f"{stem}.pdf"
    txt_name = f"{stem}.txt"
    visual_name = f"{stem}_visual.json"
    (dest_dir / pdf_name).write_bytes(raw)
    (dest_dir / txt_name).write_text(text, encoding="utf-8")

    visual = {
        "palette_hex": scan.palette_hex,
        "color_roles": scan.color_roles,
        "logo_filenames": scan.logo_filenames,
        "logo_urls": scan.logo_urls,
        "logo_placements": scan.logo_placements,
        "font_names": scan.font_names,
        "layout_hints": scan.layout_hints,
        "suggested_archetype": scan.suggested_archetype,
        "pages_scanned": scan.pages_scanned,
        "embedded_images": scan.embedded_images,
        "notes": scan.notes,
    }
    (dest_dir / visual_name).write_text(
        json.dumps(visual, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    meta = {
        "id": stem,
        "original_filename": original_filename,
        "pdf_filename": pdf_name,
        "txt_filename": txt_name,
        "visual_filename": visual_name,
        "char_count": len(text),
        "extraction_method": method,
        "url": local_url_for_brand(tenant_id, pdf_name),
        "palette_hex": scan.palette_hex,
        "color_roles": scan.color_roles,
        "logo_filenames": scan.logo_filenames,
        "logo_urls": scan.logo_urls,
        "logo_placements": scan.logo_placements,
        "font_names": scan.font_names,
        "layout_hints": scan.layout_hints,
        "suggested_archetype": scan.suggested_archetype,
        "pages_scanned": scan.pages_scanned,
        "embedded_images": scan.embedded_images,
    }
    (dest_dir / "active.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "brand_manual.saved",
        tenant_id=tenant_id,
        chars=len(text),
        method=method,
        filename=original_filename,
        palette=len(scan.palette_hex),
        logos=len(scan.logo_urls),
        fonts=len(scan.font_names),
        archetype=scan.suggested_archetype,
    )
    return {
        **meta,
        "text_preview": text[:400] + ("…" if len(text) > 400 else ""),
    }


def load_brand_text(tenant_id: str, *, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    """Carga el texto del manual activo del tenant (vacío si no hay)."""
    dest_dir = brand_dir(tenant_id)
    active_path = dest_dir / "active.json"
    if not active_path.is_file():
        return ""
    try:
        meta = json.loads(active_path.read_text(encoding="utf-8"))
        txt_name = meta.get("txt_filename") or ""
        txt_path = dest_dir / txt_name
        if not txt_path.is_file():
            return ""
        text = txt_path.read_text(encoding="utf-8").strip()
        if len(text) > max_chars:
            return text[:max_chars] + "\n…[manual truncado]"
        return text
    except Exception as exc:
        logger.warning("brand_manual.load_failed", error=str(exc), tenant_id=tenant_id)
        return ""


def get_active_brand_meta(tenant_id: str) -> dict | None:
    active_path = brand_dir(tenant_id) / "active.json"
    if not active_path.is_file():
        return None
    try:
        return json.loads(active_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_brand_visual_assets(tenant_id: str) -> dict:
    """Paleta + logos + tipografías + layout del escaneo activo."""
    meta = get_active_brand_meta(tenant_id) or {}
    dest = brand_dir(tenant_id)
    logo_filenames = list(meta.get("logo_filenames") or [])
    logo_urls = list(meta.get("logo_urls") or [])
    palette = list(meta.get("palette_hex") or [])
    font_names = list(meta.get("font_names") or [])
    layout_hints = list(meta.get("layout_hints") or [])
    logo_placements = list(meta.get("logo_placements") or [])
    color_roles = dict(meta.get("color_roles") or {})
    suggested_archetype = meta.get("suggested_archetype")

    visual_name = meta.get("visual_filename") or ""
    if visual_name and (dest / visual_name).is_file():
        try:
            visual = json.loads((dest / visual_name).read_text(encoding="utf-8"))
            palette = list(visual.get("palette_hex") or palette)
            logo_filenames = list(visual.get("logo_filenames") or logo_filenames)
            logo_urls = list(visual.get("logo_urls") or logo_urls)
            font_names = list(visual.get("font_names") or font_names)
            layout_hints = list(visual.get("layout_hints") or layout_hints)
            logo_placements = list(visual.get("logo_placements") or logo_placements)
            color_roles = dict(visual.get("color_roles") or color_roles)
            suggested_archetype = visual.get("suggested_archetype") or suggested_archetype
        except Exception as exc:
            logger.warning("brand_manual.visual_load_failed", error=str(exc))

    logo_paths = [
        str(dest / name)
        for name in logo_filenames
        if name and (dest / name).is_file()
    ]
    return {
        "palette_hex": palette,
        "color_roles": color_roles,
        "logo_filenames": logo_filenames,
        "logo_urls": logo_urls,
        "logo_paths": logo_paths,
        "font_names": font_names,
        "layout_hints": layout_hints,
        "logo_placements": logo_placements,
        "suggested_archetype": suggested_archetype,
    }


def clear_brand_manual(tenant_id: str) -> bool:
    """Quita el manual activo (no borra archivos históricos)."""
    active_path = brand_dir(tenant_id) / "active.json"
    if active_path.is_file():
        active_path.unlink()
        return True
    return False


def brand_prompt_block(brand_text: str) -> str:
    """Bloque listo para anexar al prompt de usuario de los agentes."""
    text = (brand_text or "").strip()
    if not text:
        return ""
    return (
        "\n- Brand manual / identity guidelines (MUST respect colors, tone, "
        "forbidden claims, typography notes, and visual rules):\n"
        f"{text}\n"
    )


def brand_system_addendum(brand_text: str) -> str:
    """Addendum corto al system prompt cuando hay manual cargado."""
    if not (brand_text or "").strip():
        return ""
    return (
        "\n\nBRAND MANUAL IS HIGHEST PRIORITY. Honor voice, palette, typography cues, "
        "claims policy, emotions, and visual identity from the brand manual over any "
        "generic yellow/white agency template. Never invent logo marks as readable text "
        "in image prompts; describe style instead. Imagery must feel vivid and specific "
        "to THIS client's product/service.\n"
    )
