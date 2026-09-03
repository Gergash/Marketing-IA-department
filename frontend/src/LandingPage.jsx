import { Link } from "./RouterLink";
import "./staging.css";

const NETWORKS = [
  { name: "Facebook", desc: "Posts e historias con diseño adaptado." },
  { name: "Instagram", desc: "Feed, stories y reels con subtítulos." },
  { name: "X", desc: "Imágenes y clips optimizados para la red." },
  { name: "TikTok", desc: "Videos verticales con tipografía y overlays." },
];

const FORMATS = [
  "Imágenes estáticas listas para publicar",
  "Videos con subtítulos automáticos",
  "Piezas 100% generadas con IA",
  "Tus fotos con tipografías, overlays y diseño de marca",
];

export default function LandingPage() {
  return (
    <div className="staging-page">
      <header className="staging-hero">
        <p className="staging-kicker">PowerUps · Departamento de Marketing Agéntico</p>
        <h1>Tu equipo de marketing con IA, en un solo lugar</h1>
        <p className="staging-lead">
          Crea y publica en Facebook, Instagram, X y TikTok. Genera imágenes con IA,
          edita tus fotos con subtítulos y tipografías, o produce reels con voz y diseño
          — pagando solo los créditos que uses.
        </p>
        <div className="staging-cta-row">
          <Link to="/login" className="staging-btn staging-btn-primary">
            Crear cuenta / Iniciar sesión
          </Link>
          <Link to="/app" className="staging-btn staging-btn-ghost">
            Ir al estudio
          </Link>
        </div>
      </header>

      <section className="staging-section card">
        <h2>¿Qué puedes publicar?</h2>
        <ul className="staging-list">
          {FORMATS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="staging-section">
        <h2>Redes conectadas</h2>
        <div className="staging-grid">
          {NETWORKS.map((n) => (
            <article key={n.name} className="card staging-network-card">
              <h3>{n.name}</h3>
              <p>{n.desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="staging-section card staging-pricing">
        <h2>Créditos por publicación</h2>
        <p>Cada red consume créditos según el tipo de pieza. Recarga con Bold cuando lo necesites.</p>
        <table className="staging-table">
          <thead>
            <tr>
              <th>Tipo</th>
              <th>Créditos</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Imagen estática</td>
              <td>1</td>
            </tr>
            <tr>
              <td>Imagen IA o diseño sobre tu foto</td>
              <td>2</td>
            </tr>
            <tr>
              <td>Video con subtítulos</td>
              <td>5</td>
            </tr>
            <tr>
              <td>Reel / clip con IA</td>
              <td>8</td>
            </tr>
          </tbody>
        </table>
        <Link to="/login" className="staging-btn staging-btn-primary">
          Empezar ahora
        </Link>
      </section>

      <footer className="staging-footer">
        <Link to="/terminos">Términos</Link>
        <Link to="/privacidad">Privacidad</Link>
      </footer>
    </div>
  );
}
