/** Páginas legales espejo (Vite). En producción/TikTok usan las del gateway vía ngrok. */

const UPDATED = "4 de septiembre de 2026";

function LegalShell({ title, children }) {
  return (
    <main
      style={{
        maxWidth: "42rem",
        margin: "0 auto",
        padding: "2.5rem 1.25rem 4rem",
        fontFamily: 'Georgia, "Times New Roman", serif',
        lineHeight: 1.65,
        color: "#12163a",
        background: "#f4f7fb",
        minHeight: "100vh",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem" }}>
        <img
          src="/app-icon-192.png"
          alt="Marketing Agéntico (Auto)"
          width={48}
          height={48}
          style={{ borderRadius: 10 }}
        />
        <div>
          <strong style={{ fontFamily: "system-ui, sans-serif" }}>Marketing Agéntico (Auto)</strong>
          <div style={{ fontSize: "0.85rem", color: "#5b647a", fontFamily: "system-ui, sans-serif" }}>
            PowerUps
          </div>
        </div>
      </div>
      <h1 style={{ fontSize: "1.85rem", margin: "0 0 0.35rem" }}>{title}</h1>
      <p style={{ color: "#555", fontSize: "0.95rem", marginBottom: "2rem" }}>
        Marketing Agéntico (Auto) · Departamento de Marketing Agéntico
        <br />
        Última actualización: {UPDATED}
      </p>
      {children}
    </main>
  );
}

export function TerminosPage() {
  return (
    <LegalShell title="Condiciones de servicio">
      <p>
        Estas Condiciones regulan el uso de <strong>Departamento de Marketing Agéntico</strong> /
        <strong> Marketing DEPA IA</strong>, incluido el inicio de sesión con TikTok y otras redes.
      </p>
      <h2>1. Aceptación</h2>
      <p>Al usar el Servicio acepta estas Condiciones. Si no está de acuerdo, no lo utilice.</p>
      <h2>2. Descripción</h2>
      <p>
        Generación y publicación asistida por IA de contenidos de marketing, con conexión OAuth a
        cuentas sociales que usted autorice.
      </p>
      <h2>3. Contenido y responsabilidad</h2>
      <p>
        Usted revisa y aprueba todo lo que se publica. El Servicio no garantiza resultados comerciales
        ni la aceptación por TikTok u otras plataformas.
      </p>
      <h2>4. Uso aceptable</h2>
      <p>Prohibido uso ilegal, spam, abuso de APIs o contenido que viole políticas de terceros.</p>
      <h2>5. Privacidad</h2>
      <p>
        Ver la <a href="/privacidad">Política de Privacidad</a>.
      </p>
      <h2>6. Contacto</h2>
      <p>Canal de soporte del operador del Servicio para esta prueba.</p>
      <p style={{ marginTop: "2.5rem" }}>
        <a href="/privacidad">Política de Privacidad</a>
        {" · "}
        <a href="/">Volver al panel</a>
      </p>
    </LegalShell>
  );
}

export function PrivacidadPage() {
  return (
    <LegalShell title="Políticas de privacidad">
      <p>
        Describe cómo el Servicio trata datos personales en esta prueba, incluida la integración con
        TikTok.
      </p>
      <h2>1. Datos</h2>
      <ul>
        <li>Autenticación / API key local</li>
        <li>Tokens e identificadores OAuth de redes que usted conecte</li>
        <li>Briefs, assets y manuales de marca que cargue</li>
        <li>Logs técnicos necesarios para operar el Servicio</li>
      </ul>
      <h2>2. Finalidades</h2>
      <p>Prestar el Servicio, mantener sesiones sociales, seguridad y soporte de la prueba.</p>
      <h2>3. Terceros</h2>
      <p>
        Proveedores de IA/infraestructura y APIs de TikTok, Meta u otras redes, sujetos a sus propias
        políticas.
      </p>
      <h2>4. Derechos</h2>
      <p>
        Puede solicitar acceso, rectificación o eliminación, y revocar OAuth desconectando la cuenta.
      </p>
      <h2>5. Contacto</h2>
      <p>Canal de soporte del operador del Servicio.</p>
      <p style={{ marginTop: "2.5rem" }}>
        <a href="/terminos">Condiciones de Servicio</a>
        {" · "}
        <a href="/">Volver al panel</a>
      </p>
    </LegalShell>
  );
}
