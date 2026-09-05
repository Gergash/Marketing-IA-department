import { Link } from "./RouterLink";

/** Ruta pública del icono de marca (mismo asset que TikTok App Icon + favicon). */
export const BRAND_ICON = "/app-icon-512.png";
export const BRAND_ICON_FULL = "/logo-marketing-agentico.jpg";
export const BRAND_NAME = "Marketing Agéntico";
export const BRAND_TAGLINE = "(Auto)";

export function BrandMark({ size = 40, showText = true, to = "/", className = "" }) {
  const img = (
    <img
      src={BRAND_ICON}
      alt={`${BRAND_NAME} ${BRAND_TAGLINE}`}
      width={size}
      height={size}
      className="brand-mark-img"
      decoding="async"
    />
  );
  const inner = (
    <span className={`brand-mark ${className}`}>
      {img}
      {showText && (
        <span className="brand-mark-text">
          <span className="brand-mark-name">{BRAND_NAME}</span>
          <span className="brand-mark-tag">{BRAND_TAGLINE}</span>
        </span>
      )}
    </span>
  );
  if (!to) return inner;
  return (
    <Link to={to} className="brand-mark-link" aria-label={`${BRAND_NAME} inicio`}>
      {inner}
    </Link>
  );
}
