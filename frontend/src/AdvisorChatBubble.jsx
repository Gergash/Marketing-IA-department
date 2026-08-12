import { useEffect, useRef, useState } from "react";

/**
 * Burbuja flotante del Asesor Creativo (diseñador + productor + mercadólogo).
 * `api` y `briefContext` vienen de App.jsx.
 */
export default function AdvisorChatBubble({ api, briefContext }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hola — soy tu asesor creativo (diseño, producción, marketing y marca). Cuéntame qué quieres comunicar y te digo formato, hook y CTA.",
    },
  ]);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    const nextHistory = [...messages, { role: "user", content: text }];
    setMessages(nextHistory);
    setInput("");
    setSending(true);
    try {
      const data = await api("/advisor/chat", "POST", {
        message: text,
        history: nextHistory.slice(-10).map((m) => ({ role: m.role, content: m.content })),
        brief_context: briefContext || {},
      });
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply || "…" }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `No pude responder ahora: ${err.message || err}. Revisa que el gateway y el LLM estén activos.`,
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={`advisor-bubble ${open ? "is-open" : ""}`}>
      {open && (
        <div className="advisor-panel" role="dialog" aria-label="Asesor creativo">
          <header className="advisor-header">
            <div>
              <strong>Asesor creativo</strong>
              <p className="hint" style={{ margin: 0 }}>
                Diseño · Producción · Marketing · Marca
              </p>
            </div>
            <button type="button" className="advisor-close" onClick={() => setOpen(false)} aria-label="Cerrar">
              ×
            </button>
          </header>
          <div className="advisor-messages">
            {messages.map((m, i) => (
              <div key={i} className={`advisor-msg advisor-msg-${m.role}`}>
                {m.content}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
          <div className="advisor-composer">
            <textarea
              rows={2}
              placeholder="Ej: Lanzamos un evento de networking el viernes…"
              value={input}
              disabled={sending}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button type="button" onClick={send} disabled={sending || !input.trim()}>
              {sending ? "…" : "Enviar"}
            </button>
          </div>
        </div>
      )}
      <button
        type="button"
        className="advisor-fab"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title="Asesor creativo"
      >
        {open ? "×" : "Asesor"}
      </button>
    </div>
  );
}
