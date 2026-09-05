"""Generación de imágenes: Stable Diffusion (A1111), fal.ai, Venice.ai, DALL·E, Canva placeholder y dummy."""

from __future__ import annotations

import base64
import io
import textwrap
import uuid
from pathlib import Path

import structlog

from .design_layouts import apply_design_layout
from .image_specs import fal_image_size_arg, resolve_image_spec
from .layout_archetypes import _ARCHETYPE_MAP

logger = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "images"
_SD_STEPS = 20
_DALLE_SIZE = "1792x1024"


def generate_image(
    prompt: str,
    *,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    image_provider: str | None = None,
    red_social: str = "instagram",
    content_format: str = "feed",
    layout_archetype: str = "typographic_poster",
    brand_archetype=None,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
    font_seed: str | None = None,
) -> tuple[str, int, int]:
    """Return (image URL, width, height) for the given prompt."""
    from gateway.app.core.settings import get_settings

    s = get_settings()
    provider = (image_provider or s.image_provider).strip().lower()
    spec = resolve_image_spec(red_social, content_format)
    overlay_extras = {
        "brand_archetype": brand_archetype,
        "preferred_font_paths": preferred_font_paths,
        "logo_path": logo_path,
        "tagline": tagline,
        "brand_names": brand_names,
        "font_seed": (font_seed or f"{layout_archetype}:{red_social}").strip(),
    }

    if provider == "stable_diffusion":
        url = _stable_diffusion(
            prompt,
            s.stable_diffusion_url,
            spec=spec,
            checkpoint=(s.stable_diffusion_checkpoint or "").strip() or None,
            overlay_text=overlay_text,
            overlay_subline=overlay_subline,
            overlay_cta=overlay_cta,
            red_social=red_social,
            layout_archetype=layout_archetype,
            content_format=content_format,
            **overlay_extras,
        )
        return url, spec.width, spec.height
    if provider == "fal" and s.fal_api_key:
        url = _fal(
            prompt,
            s.fal_api_key,
            s.fal_model,
            spec=spec,
            overlay_text=overlay_text,
            overlay_subline=overlay_subline,
            overlay_cta=overlay_cta,
            red_social=red_social,
            layout_archetype=layout_archetype,
            content_format=content_format,
            **overlay_extras,
        )
        return url, spec.width, spec.height
    if provider == "fal" and not s.fal_api_key:
        logger.error("image.fal_missing_key")
        raise RuntimeError("image_gen_failed:fal: missing API key")
    if provider == "venice" and s.venice_api_key:
        url = _venice(
            prompt,
            s.venice_api_key,
            s.venice_api_base,
            s.venice_image_model,
            style_preset=(s.venice_image_style_preset or "").strip() or None,
            resolution=(s.venice_image_resolution or "2K").strip() or "2K",
            spec=spec,
            overlay_text=overlay_text,
            overlay_subline=overlay_subline,
            overlay_cta=overlay_cta,
            red_social=red_social,
            layout_archetype=layout_archetype,
            content_format=content_format,
            **overlay_extras,
        )
        return url, spec.width, spec.height
    if provider == "venice" and not s.venice_api_key:
        logger.error("image.venice_missing_key")
        raise RuntimeError("image_gen_failed:venice: missing API key")
    if provider == "openai" and s.openai_api_key:
        url = _dalle(prompt, s.openai_api_key)
        return url, spec.width, spec.height
    if provider == "canva":
        url = _canva(prompt, s)
        return url, spec.width, spec.height
    url = _placeholder(prompt, spec=spec)
    return url, spec.width, spec.height


def _stable_diffusion(
    prompt: str,
    sd_url: str,
    *,
    spec,
    checkpoint: str | None,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    red_social: str = "instagram",
    layout_archetype: str = "typographic_poster",
    content_format: str = "feed",
    brand_archetype=None,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
    font_seed: str | None = None,
) -> str:
    """POST a txt2img de A1111/Forge, decodifica PNG, superpone texto y guarda en `/static/images/`."""
    import httpx

    from .visual_prompt_guards import NO_TEXT_NEGATIVE, with_photo_only_guard

    payload: dict = {
        "prompt": with_photo_only_guard(
            f"{prompt[:400]}. Clean photographic composition, aspect {spec.label}."
        ),
        "negative_prompt": NO_TEXT_NEGATIVE,
        "width": spec.width,
        "height": spec.height,
        "steps": _SD_STEPS,
        "cfg_scale": 7,
        "sampler_name": "Euler a",
        "n_iter": 1,
        "batch_size": 1,
    }
    if checkpoint:
        payload["override_settings"] = {"sd_model_checkpoint": checkpoint}

    try:
        resp = httpx.post(sd_url, json=payload, timeout=300)
        resp.raise_for_status()
        images = resp.json().get("images", [])
        if not images:
            logger.warning("image.sd_empty_response")
            raise RuntimeError("image_gen_failed:stable_diffusion: empty response")

        raw = base64.b64decode(images[0])

        if overlay_text:
            raw = _apply_layout_overlay(
                raw,
                overlay_text,
                overlay_subline,
                overlay_cta,
                layout_archetype=layout_archetype,
                font_seed=font_seed or red_social,
                content_format=content_format,
                brand_archetype=brand_archetype,
                preferred_font_paths=preferred_font_paths,
                logo_path=logo_path,
                tagline=tagline,
                brand_names=brand_names,
            )

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        (_STATIC_DIR / filename).write_bytes(raw)
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.sd_generated", url=url, size=f"{spec.width}x{spec.height}")
        return url
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("image.sd_error", error=str(exc))
        raise RuntimeError(
            f"image_gen_failed:stable_diffusion: {exc}. "
            "Arranca A1111/Forge en STABLE_DIFFUSION_URL o elige fal.ai en el dashboard."
        ) from exc


def _apply_layout_overlay(
    raw: bytes,
    headline: str,
    subline: str | None,
    cta: str | None,
    *,
    layout_archetype: str,
    font_seed: str,
    content_format: str = "feed",
    brand_archetype=None,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
) -> bytes:
    """Aplica composición editorial según arquetipo (poster, campaña marca, hero…)."""
    archetype = brand_archetype or _ARCHETYPE_MAP.get(
        layout_archetype, _ARCHETYPE_MAP["typographic_poster"]
    )
    return apply_design_layout(
        raw,
        archetype,
        headline,
        subline,
        cta,
        font_seed=font_seed,
        content_format=content_format,
        preferred_font_paths=preferred_font_paths,
        logo_path=logo_path,
        tagline=tagline,
        brand_names=brand_names,
    )


def _fal(
    prompt: str,
    api_key: str,
    model: str = "fal-ai/flux-pro/v1.1",
    *,
    spec,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    red_social: str = "instagram",
    layout_archetype: str = "typographic_poster",
    content_format: str = "feed",
    brand_archetype=None,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
    font_seed: str | None = None,
) -> str:
    """Genera imagen con fal.ai (Flux pro u otros modelos) y la guarda en static/images/."""
    import os

    import httpx

    os.environ.setdefault("FAL_KEY", api_key)

    try:
        import fal_client  # pip install fal-client
    except ImportError:
        logger.error("image.fal_missing_sdk", hint="pip install fal-client")
        raise RuntimeError("image_gen_failed:fal: fal_client not installed") from None

    from .visual_prompt_guards import with_photo_only_guard

    visual_prompt = with_photo_only_guard(
        f"{prompt[:1800]}. Aspect ratio {spec.label}."
    )
    try:
        result = fal_client.run(
            model,
            arguments={
                "prompt": visual_prompt,
                "image_size": fal_image_size_arg(spec),
                "num_inference_steps": 28,
                "num_images": 1,
                "enable_safety_checker": False,
            },
        )
        image_url: str = result["images"][0]["url"]
        logger.info(
            "image.fal_generated",
            model=model,
            size=f"{spec.width}x{spec.height}",
            url=image_url[:80],
            prompt_preview=visual_prompt[:160],
        )
    except Exception as exc:
        logger.error("image.fal_api_error", error=str(exc), prompt_preview=visual_prompt[:160])
        raise RuntimeError(f"image_gen_failed:fal: {exc}") from exc

    try:
        img_resp = httpx.get(image_url, timeout=60, follow_redirects=True)
        img_resp.raise_for_status()
        raw = img_resp.content

        if overlay_text:
            raw = _apply_layout_overlay(
                raw,
                overlay_text,
                overlay_subline,
                overlay_cta,
                layout_archetype=layout_archetype,
                font_seed=font_seed or red_social,
                content_format=content_format,
                brand_archetype=brand_archetype,
                preferred_font_paths=preferred_font_paths,
                logo_path=logo_path,
                tagline=tagline,
                brand_names=brand_names,
            )

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"fal_{uuid.uuid4().hex}.png"
        (_STATIC_DIR / filename).write_bytes(raw)
        local_url = f"http://localhost:8000/static/images/{filename}"
        # Sin overlay: Shotstack puede bajar directo de fal.media (evita ngrok/interstitial).
        # Con overlay Pillow el bytes cambió → hay que servir el PNG local vía PUBLIC_IMAGE_BASE_URL.
        if overlay_text:
            logger.info("image.fal_saved", url=local_url, source="local_overlay")
            return local_url
        logger.info("image.fal_saved", url=local_url, source="fal_cdn", cdn_url=image_url[:80])
        return image_url
    except Exception as exc:
        logger.error("image.fal_download_error", error=str(exc))
        raise RuntimeError(f"image_gen_failed:fal:download: {exc}") from exc


def _venice(
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    *,
    style_preset: str | None,
    resolution: str | None = None,
    spec,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    red_social: str = "instagram",
    layout_archetype: str = "typographic_poster",
    content_format: str = "feed",
    brand_archetype=None,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
    font_seed: str | None = None,
) -> str:
    """Genera imagen con Venice.ai (/image/generate) y la guarda en static/images/."""
    from .user_assets import fit_image_to_spec
    from .venice_client import generate_image_bytes, truncate_prompt
    from .visual_prompt_guards import (
        NO_TEXT_NEGATIVE,
        NO_TEXT_NEGATIVE_WITH_PEOPLE,
        with_photo_only_guard,
    )

    want_people = "critical scene requirement" in (prompt or "").lower() or (
        "includes the requested people" in (prompt or "").lower()
    )
    # Prompt acotado al límite del modelo (sd35=1500; gpt-image-2=4000; nano-banana≈7500).
    # Si el diseñador ya antepuso CRITICAL REVISION, truncate corta la cola (base), no la revisión.
    guarded = with_photo_only_guard(
        f"{prompt}. Aspect ratio {spec.label}.",
        allow_people=want_people,
    )
    visual_prompt = truncate_prompt(guarded, model)
    try:
        raw = generate_image_bytes(
            visual_prompt,
            api_key=api_key,
            base_url=base_url,
            model=model,
            width=spec.width,
            height=spec.height,
            negative_prompt=NO_TEXT_NEGATIVE_WITH_PEOPLE if want_people else NO_TEXT_NEGATIVE,
            style_preset=style_preset,
            resolution=resolution,
            fmt="png",
        )
    except Exception as exc:
        logger.error("image.venice_api_error", error=str(exc), prompt_preview=visual_prompt[:160])
        raise RuntimeError(f"image_gen_failed:venice: {exc}") from exc

    try:
        raw = fit_image_to_spec(raw, spec)
    except Exception as exc:
        logger.warning("image.venice_fit_skipped", error=str(exc))

    if overlay_text:
        raw = _apply_layout_overlay(
            raw,
            overlay_text,
            overlay_subline,
            overlay_cta,
            layout_archetype=layout_archetype,
            font_seed=font_seed or red_social,
            content_format=content_format,
            brand_archetype=brand_archetype,
            preferred_font_paths=preferred_font_paths,
            logo_path=logo_path,
            tagline=tagline,
            brand_names=brand_names,
        )

    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"venice_{uuid.uuid4().hex}.png"
    (_STATIC_DIR / filename).write_bytes(raw)
    local_url = f"http://localhost:8000/static/images/{filename}"
    logger.info(
        "image.venice_generated",
        url=local_url,
        model=model,
        size=f"{spec.width}x{spec.height}",
    )
    return local_url


def _dalle(prompt: str, api_key: str) -> str:
    """Genera imagen con DALL·E 3 y devuelve la URL remota de OpenAI."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt[:4000],
            size=_DALLE_SIZE,
            quality="standard",
            n=1,
        )
        url = resp.data[0].url
        logger.info("image.dalle_generated", url=url[:80] if url else "")
        return url or _placeholder(prompt)
    except Exception as exc:
        logger.error("image.dalle_error", error=str(exc))
        return _placeholder(prompt)


def _canva(prompt: str, settings) -> str:
    """Placeholder: Canva requiere OAuth; devuelve placeholder si no está implementado."""
    if not settings.canva_client_id:
        logger.warning("image.canva_not_configured")
        return _placeholder(prompt)
    logger.warning("image.canva_oauth_not_implemented")
    return _placeholder(prompt)


def _placeholder(prompt: str, *, spec=None) -> str:
    """Genera imagen placeholder local con Pillow para desarrollo sin GPU ni APIs."""
    if spec is None:
        spec = resolve_image_spec("instagram", "feed")
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (spec.width, spec.height), color=(26, 32, 44))
        draw = ImageDraw.Draw(img)

        try:
            font_big = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", size=22)
            font_small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size=15)
        except Exception:
            font_big = ImageFont.load_default()
            font_small = font_big

        label = f"[MOCK — {spec.width}x{spec.height}]"
        draw.text((20, 20), label, font=font_big, fill=(255, 130, 0))

        wrapped = textwrap.fill(prompt[:200], width=max(30, spec.width // 14))
        draw.text((20, 60), wrapped, font=font_small, fill=(200, 200, 200))

        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"mock_{uuid.uuid4().hex}.png"
        img.save(_STATIC_DIR / filename, format="PNG")
        url = f"http://localhost:8000/static/images/{filename}"
        logger.info("image.placeholder_generated", url=url)
        return url
    except Exception as exc:
        logger.warning("image.placeholder_fallback", error=str(exc))
        text = prompt[:50].replace(" ", "+")
        return f"https://dummyimage.com/{spec.width}x{spec.height}/1a202c/ffffff&text={text}"


def compose_from_user_asset(
    user_asset_url: str,
    *,
    spec,
    overlay_text: str | None = None,
    overlay_subline: str | None = None,
    overlay_cta: str | None = None,
    red_social: str = "instagram",
    layout_archetype: str = "typographic_poster",
    content_format: str = "feed",
    alter_with_ai: bool = False,
    visual_instructions: str | None = None,
    revision_notes: str | None = None,
    image_provider: str | None = None,
    brand_archetype=None,
    preferred_font_paths: list[str] | None = None,
    logo_path: str | None = None,
    tagline: str | None = None,
    brand_names: list[str] | None = None,
    font_seed: str | None = None,
) -> tuple[str, int, int, str]:
    """
    Design-as-Code: foto del usuario como capa base + overlay Pillow.
    Si alter_with_ai=True, edita la foto con Venice (/image/edit) o fal img2img
    antes del overlay tipográfico.
    Retorna (url, width, height, design_source).
    """
    from gateway.app.core.settings import get_settings

    from .user_assets import fit_image_to_spec, load_asset_bytes, save_composed_image

    s = get_settings()
    raw = load_asset_bytes(user_asset_url)
    fitted = fit_image_to_spec(raw, spec)

    design_source = "user_overlay"
    if alter_with_ai:
        from .revision_prompt import build_scene_edit_prompt

        provider = (image_provider or s.image_provider).strip().lower()
        # Solo escena (personas/objetos). NUNCA el prompt Flux ni el copy tipográfico:
        # si el modelo recibe headlines, pinta letras ilegibles en el bitmap.
        prompt = build_scene_edit_prompt(
            visual_instructions,
            revision_notes=revision_notes,
        )
        logger.info(
            "user_asset.scene_edit_prompt",
            provider=provider,
            prompt_preview=prompt[:220],
        )
        if provider == "venice" and s.venice_api_key:
            fitted = _venice_edit(
                fitted,
                prompt,
                api_key=s.venice_api_key,
                base_url=s.venice_api_base,
                generate_model=s.venice_image_model,
                edit_model=(s.venice_image_edit_model or "").strip() or None,
                resolution=(s.venice_image_resolution or "2K").strip() or "2K",
                spec=spec,
            )
            design_source = "user_img2img"
        elif provider == "fal" and s.fal_api_key:
            fitted = _fal_img2img(
                fitted,
                prompt,
                s.fal_api_key,
                s.fal_img2img_model,
                strength=s.fal_img2img_strength,
                spec=spec,
            )
            design_source = "user_img2img"
        else:
            logger.warning(
                "user_asset.img2img_skipped",
                reason="alter_with_ai requiere IMAGE_PROVIDER=venice (edit) o fal (img2img) con API key",
                provider=provider,
            )
            raise RuntimeError(
                "image_edit_unavailable: activa IMAGE_PROVIDER=venice (gpt-image-2-edit) "
                "o fal para modificar fotos reales con IA."
            )

    if overlay_text:
        fitted = _apply_layout_overlay(
            fitted,
            overlay_text,
            overlay_subline,
            overlay_cta,
            layout_archetype=layout_archetype,
            font_seed=font_seed or red_social,
            content_format=content_format,
            brand_archetype=brand_archetype,
            preferred_font_paths=preferred_font_paths,
            logo_path=logo_path,
            tagline=tagline,
            brand_names=brand_names,
        )

    prefix = "user_img2img" if design_source == "user_img2img" else "user_overlay"
    url, w, h = save_composed_image(fitted, prefix=prefix)
    logger.info("user_asset.composed", source=design_source, url=url)
    return url, w, h, design_source


def _venice_edit(
    img_bytes: bytes,
    prompt: str,
    *,
    api_key: str,
    base_url: str,
    generate_model: str,
    edit_model: str | None,
    resolution: str,
    spec,
) -> bytes:
    """Edita foto real vía Venice POST /image/edit (p.ej. gpt-image-2-edit)."""
    from .venice_client import edit_image_bytes, edit_model_for_generate_model, venice_aspect_ratio

    model = (edit_model or "").strip() or edit_model_for_generate_model(generate_model)
    # El prompt ya viene de build_scene_edit_prompt (sin tipografía).
    # No enviar quality: el schema vivo de /image/edit lo rechaza (400).
    edit_prompt = (prompt or "").strip()
    try:
        out = edit_image_bytes(
            img_bytes,
            edit_prompt,
            api_key=api_key,
            base_url=base_url,
            model=model,
            resolution=resolution,
            aspect_ratio=venice_aspect_ratio(spec.width, spec.height),
        )
        logger.info("image.venice_edit_ok", model=model, out_bytes=len(out))
        return out
    except Exception as exc:
        logger.error("image.venice_edit_error", error=str(exc), model=model)
        raise RuntimeError(f"image_gen_failed:venice_edit: {exc}") from exc


def _fal_img2img(
    img_bytes: bytes,
    prompt: str,
    api_key: str,
    model: str,
    *,
    strength: float,
    spec,
) -> bytes:
    """Alteración controlada vía fal image-to-image; devuelve bytes PNG."""
    import os
    import tempfile

    import httpx

    os.environ.setdefault("FAL_KEY", api_key)

    try:
        import fal_client
    except ImportError as exc:
        logger.error("image.fal_missing_sdk", hint="pip install fal-client")
        raise RuntimeError("image_gen_failed: fal_img2img: pip install fal-client") from exc

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name
        uploaded_url = fal_client.upload_file(tmp_path)
        result = fal_client.run(
            model,
            arguments={
                "prompt": prompt[:2000],
                "image_url": uploaded_url,
                "strength": strength,
                "image_size": fal_image_size_arg(spec),
                "num_inference_steps": 28,
                "enable_safety_checker": False,
            },
        )
        out_url: str = result["images"][0]["url"]
        resp = httpx.get(out_url, timeout=90, follow_redirects=True)
        resp.raise_for_status()
        logger.info("image.fal_img2img_ok", model=model)
        return resp.content
    except Exception as exc:
        logger.error("image.fal_img2img_error", error=str(exc))
        # No devolver la foto original en silencio: el usuario cree que "alteró" y
        # solo ve overlay tipográfico (sillas vacías + textos).
        raise RuntimeError(f"image_gen_failed: fal_img2img: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
