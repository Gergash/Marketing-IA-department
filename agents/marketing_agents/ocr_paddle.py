"""OCR local con PaddleOCR (fallback para PDFs escaneados / sin texto embebido).

Diseñado para GPUs modestas (p. ej. GTX 1650 Ti 4GB): modelos mobile cuando
estén disponibles; lazy singleton para no recargar pesos en cada upload.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_ocr_engine = None
_ocr_init_error: str | None = None


def reset_ocr_engine() -> None:
    """Solo para tests."""
    global _ocr_engine, _ocr_init_error
    _ocr_engine = None
    _ocr_init_error = None


def _get_engine(*, lang: str, use_gpu: bool):
    global _ocr_engine, _ocr_init_error
    if _ocr_engine is not None:
        return _ocr_engine
    if _ocr_init_error:
        raise RuntimeError(_ocr_init_error)

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        _ocr_init_error = (
            "Falta paddleocr/paddlepaddle. Instala con: "
            "pip install paddlepaddle paddleocr pymupdf"
        )
        raise RuntimeError(_ocr_init_error) from exc

    # Intento 3.x (mobile, apto 4GB) → 2.x clásico.
    attempts: list[dict] = [
        {
            "lang": lang,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "text_detection_model_name": "PP-OCRv5_mobile_det",
            "text_recognition_model_name": "PP-OCRv5_mobile_rec",
        },
        {
            "lang": lang,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {"lang": lang, "use_angle_cls": True, "use_gpu": use_gpu},
        {"lang": "en", "use_angle_cls": True, "use_gpu": use_gpu},
        {"lang": lang},
    ]
    last_exc: Exception | None = None
    for kwargs in attempts:
        try:
            _ocr_engine = PaddleOCR(**kwargs)
            logger.info("ocr.paddle_ready", kwargs={k: kwargs[k] for k in kwargs if k != "lang"}, lang=kwargs.get("lang"))
            return _ocr_engine
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("ocr.paddle_init_attempt_failed", error=str(exc), keys=list(kwargs.keys()))

    _ocr_init_error = f"No se pudo inicializar PaddleOCR: {last_exc}"
    raise RuntimeError(_ocr_init_error) from last_exc


def pdf_bytes_to_png_pages(raw: bytes, *, max_pages: int, dpi: int) -> list[bytes]:
    """Rasteriza páginas del PDF a PNG en memoria (PyMuPDF)."""
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "Falta pymupdf para rasterizar PDF. Instala con: pip install pymupdf"
        ) from exc

    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pages: list[bytes] = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pages.append(pix.tobytes("png"))
        return pages
    finally:
        doc.close()


def _lines_from_ocr_result(result) -> list[str]:
    """Normaliza salidas 2.x (lista anidada) y 3.x (objetos / dict)."""
    lines: list[str] = []
    if result is None:
        return lines

    # 3.x: lista de objetos con .json / .get("rec_texts")
    if isinstance(result, list) and result and not isinstance(result[0], list):
        for item in result:
            texts = None
            if hasattr(item, "get"):
                texts = item.get("rec_texts") or item.get("rec_text")
            if texts is None and hasattr(item, "json"):
                payload = item.json if not callable(item.json) else item.json()
                if isinstance(payload, dict):
                    texts = payload.get("rec_texts") or payload.get("rec_text")
                    if texts is None and isinstance(payload.get("res"), dict):
                        texts = payload["res"].get("rec_texts")
            if isinstance(texts, str):
                lines.append(texts.strip())
            elif isinstance(texts, list):
                for t in texts:
                    if isinstance(t, str) and t.strip():
                        lines.append(t.strip())
                    elif isinstance(t, (list, tuple)) and t:
                        lines.append(str(t[0]).strip())
            # 2.x mixed: item is page lines
            if texts is None and isinstance(item, list):
                for row in item:
                    if isinstance(row, (list, tuple)) and len(row) >= 2:
                        pair = row[1]
                        if isinstance(pair, (list, tuple)) and pair:
                            lines.append(str(pair[0]).strip())
        return [ln for ln in lines if ln]

    # 2.x clásico: result = [ [ [box, (text, conf)], ... ] ]  o una página
    pages = result if isinstance(result, list) else [result]
    for page in pages:
        if not page:
            continue
        if isinstance(page, dict):
            texts = page.get("rec_texts") or []
            for t in texts:
                if str(t).strip():
                    lines.append(str(t).strip())
            continue
        for row in page:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                pair = row[1]
                if isinstance(pair, (list, tuple)) and pair:
                    lines.append(str(pair[0]).strip())
                elif isinstance(pair, str):
                    lines.append(pair.strip())
    return [ln for ln in lines if ln]


def ocr_image_bytes(img_bytes: bytes, *, lang: str, use_gpu: bool) -> str:
    """OCR de una imagen PNG/JPEG en bytes."""
    engine = _get_engine(lang=lang, use_gpu=use_gpu)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(img_bytes)
        path = tmp.name
    try:
        result = None
        if hasattr(engine, "predict"):
            try:
                result = engine.predict(path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ocr.paddle_predict_failed", error=str(exc))
        if result is None and hasattr(engine, "ocr"):
            try:
                result = engine.ocr(path)
            except TypeError:
                result = engine.ocr(path, cls=True)
        lines = _lines_from_ocr_result(result)
        return "\n".join(lines).strip()
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def ocr_pdf_bytes(
    raw: bytes,
    *,
    lang: str = "es",
    use_gpu: bool = True,
    max_pages: int = 40,
    dpi: int = 200,
) -> str:
    """Rasteriza PDF y aplica PaddleOCR página a página."""
    pages = pdf_bytes_to_png_pages(raw, max_pages=max_pages, dpi=dpi)
    if not pages:
        return ""
    chunks: list[str] = []
    for i, png in enumerate(pages, 1):
        try:
            text = ocr_image_bytes(png, lang=lang, use_gpu=use_gpu)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ocr.paddle_page_failed", page=i, error=str(exc))
            continue
        if text:
            chunks.append(text)
            logger.info("ocr.paddle_page_ok", page=i, chars=len(text))
    return "\n\n".join(chunks).strip()
