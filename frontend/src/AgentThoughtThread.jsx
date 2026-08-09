import { useEffect, useMemo, useRef, useState } from "react";

// Cara visible de cada agente del studio; el backend manda el nombre, aquí solo el icono.
const AGENT_ICONS = {
  pipeline: "🏢",
  strategist: "🧭",
  copywriter: "✍️",
  qa: "🛡️",
  designer: "🎨",
  video_designer: "🎬",
  clip_reel_designer: "🎞️",
  publisher: "📣",
};

const PHASE_LABELS = {
  start: "arranca",
  thinking: "trabajando",
  output: "entrega",
  question: "te pregunta",
  answer: "tu respuesta",
  error: "error",
  end: "cierre",
};

const POLL_MS = 1200;

/** Campos del `data` que ya se leen en el texto del evento o no aportan nada al usuario. */
const HIDDEN_DATA_KEYS = new Set(["draft", "source", "action"]);

function formatValue(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "sí" : "no";
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value);
}

function summaryRows(data) {
  return Object.entries(data || {}).filter(
    ([key, value]) =>
      !HIDDEN_DATA_KEYS.has(key) &&
      value !== "" &&
      value !== null &&
      value !== undefined &&
      !(Array.isArray(value) && value.length === 0)
  );
}

/** Pregunta abierta = la última sin un evento `answer` posterior para el mismo checkpoint. */
function findOpenQuestion(events) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event.phase !== "question") continue;
    const answered = events
      .slice(i + 1)
      .some((later) => later.phase === "answer" && later.checkpoint === event.checkpoint);
    return answered ? null : event;
  }
  return null;
}

/**
 * Hilo de pensamiento del Marketing Studio: qué está haciendo cada agente durante el run
 * y, en modo interactivo, los puntos donde el usuario puede redirigirlos.
 */
export default function AgentThoughtThread({ api, traceId, active }) {
  const [events, setEvents] = useState([]);
  const [notes, setNotes] = useState("");
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState(null);
  const sinceRef = useRef(0);
  const bottomRef = useRef(null);

  // Cada run estrena traza: limpiar para no mezclar el pensamiento de dos piezas.
  useEffect(() => {
    setEvents([]);
    setNotes("");
    setReplyError(null);
    sinceRef.current = 0;
  }, [traceId]);

  const openQuestion = useMemo(() => findOpenQuestion(events), [events]);

  // Mientras haya una pregunta abierta se sigue consultando aunque el run ya no esté "activo":
  // en sync el POST no ha vuelto todavía y es justo cuando el agente espera respuesta.
  const shouldPoll = Boolean(traceId) && (active || Boolean(openQuestion));

  useEffect(() => {
    if (!shouldPoll) return undefined;
    let cancelled = false;

    const tick = async () => {
      try {
        const page = await api(`/thoughts/${traceId}?since=${sinceRef.current}`);
        if (cancelled) return;
        if (page.events?.length) {
          sinceRef.current = page.next_since;
          setEvents((prev) => [...prev, ...page.events]);
        }
      } catch {
        /* el poll es best-effort: un fallo puntual no debe romper el dashboard */
      }
    };

    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [shouldPoll, traceId, api]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);

  const answer = async (action) => {
    if (sending || !openQuestion) return;
    const trimmed = notes.trim();
    if (action === "adjust" && !trimmed) {
      setReplyError("Escribe qué quieres cambiar para que el agente pueda aplicarlo.");
      return;
    }
    setSending(true);
    setReplyError(null);
    try {
      await api(`/thoughts/${traceId}/reply`, "POST", {
        action,
        notes: action === "adjust" ? trimmed : "",
        checkpoint: openQuestion.checkpoint || "",
      });
      setNotes("");
    } catch (e) {
      setReplyError(e.message);
    } finally {
      setSending(false);
    }
  };

  if (!traceId || (events.length === 0 && !active)) return null;

  return (
    <section className="card thought-thread">
      <h2>
        Hilo de pensamiento del equipo
        {active && <span className="spinner spinner-dark" style={{ marginLeft: "0.5rem" }}></span>}
      </h2>
      <p className="hint">
        Cada agente cuenta qué está haciendo mientras se ejecuta el run. En modo interactivo se
        detiene en los puntos clave a esperar tus indicaciones.
      </p>

      <ol className="thought-list">
        {events.map((event) => {
          const rows = summaryRows(event.data);
          return (
            <li key={event.id} className={`thought-item thought-${event.phase}`}>
              <span className="thought-icon" aria-hidden="true">
                {AGENT_ICONS[event.agent] || "🤖"}
              </span>
              <div className="thought-body">
                <p className="thought-head">
                  <strong>{event.agent_label}</strong>
                  <span className="thought-phase">{PHASE_LABELS[event.phase] || event.phase}</span>
                </p>
                <p className="thought-message">{event.message}</p>
                {rows.length > 0 && (
                  <details className="thought-detail">
                    <summary>Ver detalle</summary>
                    <dl>
                      {rows.map(([key, value]) => (
                        <div key={key}>
                          <dt>{key}</dt>
                          <dd>{formatValue(value)}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                )}
              </div>
            </li>
          );
        })}
        <li ref={bottomRef} />
      </ol>

      {openQuestion && (
        <div className="thought-prompt">
          <p className="thought-prompt-question">
            {AGENT_ICONS[openQuestion.agent] || "🤖"} <strong>{openQuestion.agent_label}</strong>{" "}
            espera tu respuesta: {openQuestion.message}
          </p>
          <label>
            Tus indicaciones (solo si vas a ajustar)
            <textarea
              rows={2}
              placeholder="Ej: enfócalo a dueños de pymes, tono más directo, sin tecnicismos…"
              value={notes}
              disabled={sending}
              onChange={(e) => {
                setNotes(e.target.value);
                setReplyError(null);
              }}
            />
          </label>
          <div className="actions">
            {(openQuestion.options?.length
              ? openQuestion.options
              : [
                  { action: "continue", label: "Seguir así" },
                  { action: "adjust", label: "Ajustar con mis notas" },
                  { action: "cancel", label: "Detener el run" },
                ]
            ).map((option) => (
              <button
                key={option.action}
                type="button"
                disabled={sending}
                className={option.action === "cancel" ? "thought-cancel" : ""}
                onClick={() => answer(option.action)}
              >
                {option.label}
              </button>
            ))}
          </div>
          {replyError && <p className="hint thought-error">{replyError}</p>}
          <p className="hint">
            Si no respondes, el equipo continúa con su propio criterio pasado el tiempo de espera.
          </p>
        </div>
      )}
    </section>
  );
}
