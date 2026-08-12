"""Hilo de pensamiento del Marketing Studio: eventos en vivo + participación del usuario.

Cada agente publica lo que está haciendo en un stream identificado por `trace_id`
(lo genera el cliente antes del POST, porque `/runs/sync` no devuelve el `run_id`
hasta que termina). En modo interactivo el pipeline se detiene en checkpoints y
espera una respuesta del usuario por el mismo canal.

Transporte dual: Redis cuando está disponible (obligatorio para runs de Celery,
que corren en otro proceso) con degradado a memoria del proceso (suficiente para
`/runs/sync`, donde pipeline y endpoints comparten el uvicorn).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)

# Nombre humano de cada agente para que el usuario lea "quién" habla, no un id técnico.
AGENT_LABELS: dict[str, str] = {
    "pipeline": "Marketing Studio",
    "strategist": "Estratega de contenido",
    "copywriter": "Copywriter",
    "qa": "QA / Compliance",
    "designer": "Director de arte",
    "video_designer": "Diseñador de video",
    "clip_reel_designer": "Editor de clips",
    "publisher": "Publicador",
}

# Checkpoints donde el usuario puede intervenir, en orden de aparición.
CHECKPOINT_STRATEGY = "strategy"
CHECKPOINT_COPY = "copy"
CHECKPOINT_DESIGN = "design"

DEFAULT_OPTIONS: tuple[dict[str, str], ...] = (
    {"action": "continue", "label": "Seguir así"},
    {"action": "adjust", "label": "Ajustar con mis notas"},
    {"action": "cancel", "label": "Detener el run"},
)

_VALID_ACTIONS = frozenset({"continue", "adjust", "cancel"})


class RunCancelledByUser(RuntimeError):
    """El usuario detuvo el run desde un checkpoint del hilo de pensamiento."""

    def __init__(self, checkpoint: str, notes: str = "") -> None:
        super().__init__(f"Run detenido por el usuario en el checkpoint '{checkpoint}'")
        self.checkpoint = checkpoint
        self.notes = notes


# ---------------------------------------------------------------------------
# Transportes
# ---------------------------------------------------------------------------

class _MemoryBackend:
    """Cola en memoria del proceso; sirve a `/runs/sync` cuando Redis no está."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._events: dict[str, list[dict]] = {}
        self._replies: dict[str, list[dict]] = {}

    def append(self, trace_id: str, event: dict) -> None:
        with self._cond:
            self._events.setdefault(trace_id, []).append(event)
            self._cond.notify_all()

    def read(self, trace_id: str, since: int) -> list[dict]:
        with self._cond:
            return list(self._events.get(trace_id, [])[max(since, 0):])

    def push_reply(self, trace_id: str, reply: dict) -> None:
        with self._cond:
            self._replies.setdefault(trace_id, []).append(reply)
            self._cond.notify_all()

    def pop_reply(self, trace_id: str, timeout_s: float) -> dict | None:
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while True:
                pending = self._replies.get(trace_id)
                if pending:
                    return pending.pop(0)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)


class _RedisBackend:
    """Listas Redis con TTL; único transporte que ve el worker de Celery."""

    def __init__(self, client, ttl_seconds: int) -> None:
        self._client = client
        self._ttl = ttl_seconds

    @staticmethod
    def _events_key(trace_id: str) -> str:
        return f"thoughts:events:{trace_id}"

    @staticmethod
    def _replies_key(trace_id: str) -> str:
        return f"thoughts:replies:{trace_id}"

    def append(self, trace_id: str, event: dict) -> None:
        key = self._events_key(trace_id)
        pipe = self._client.pipeline()
        pipe.rpush(key, json.dumps(event, ensure_ascii=False))
        pipe.expire(key, self._ttl)
        pipe.execute()

    def read(self, trace_id: str, since: int) -> list[dict]:
        raw = self._client.lrange(self._events_key(trace_id), max(since, 0), -1)
        return [json.loads(item) for item in raw]

    def push_reply(self, trace_id: str, reply: dict) -> None:
        key = self._replies_key(trace_id)
        pipe = self._client.pipeline()
        pipe.rpush(key, json.dumps(reply, ensure_ascii=False))
        pipe.expire(key, self._ttl)
        pipe.execute()

    def pop_reply(self, trace_id: str, timeout_s: float) -> dict | None:
        # BLPOP solo acepta segundos enteros; 0 significaría "esperar para siempre".
        item = self._client.blpop(self._replies_key(trace_id), timeout=max(1, int(timeout_s)))
        return json.loads(item[1]) if item else None


_backend_lock = threading.Lock()
_backend = None


def get_backend():
    """Devuelve el transporte activo, resolviendo Redis una sola vez por proceso."""
    global _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        _backend = _resolve_backend()
        return _backend


def _resolve_backend():
    from gateway.app.core.settings import get_settings

    settings = get_settings()
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return _RedisBackend(client, settings.thoughts_ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("thoughts.redis_unavailable", error=str(exc), fallback="memory")
        return _MemoryBackend()


def supports_cross_process() -> bool:
    """True si el transporte es Redis; en memoria un worker de Celery nunca vería las respuestas."""
    return isinstance(get_backend(), _RedisBackend)


def reset_backend(backend=None) -> None:
    """Fija (o limpia) el transporte; usado por tests y por arranques en frío."""
    global _backend
    with _backend_lock:
        _backend = backend


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------

class ThoughtStream:
    """Canal de un run: publica lo que piensa cada agente y recoge la respuesta del usuario."""

    enabled = True

    def __init__(
        self,
        trace_id: str,
        *,
        interactive: bool = False,
        backend=None,
        checkpoint_timeout_s: float | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.interactive = interactive
        self._backend = backend or get_backend()
        self._checkpoint_timeout_s = checkpoint_timeout_s or _default_timeout()

    def emit(
        self,
        agent: str,
        phase: str,
        message: str,
        *,
        data: dict | None = None,
        checkpoint: str | None = None,
        options: tuple | list | None = None,
    ) -> dict:
        """Publica un evento del hilo; nunca rompe el run si el transporte falla."""
        event = {
            "id": uuid.uuid4().hex,
            "trace_id": self.trace_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "agent_label": AGENT_LABELS.get(agent, agent),
            "phase": phase,
            "message": message,
            "data": data or {},
            "checkpoint": checkpoint,
            "options": [dict(o) for o in (options or [])],
        }
        try:
            self._backend.append(self.trace_id, event)
        except Exception as exc:  # noqa: BLE001
            logger.warning("thoughts.emit_error", error=str(exc), agent=agent)
        return event

    def think(self, agent: str, message: str, **data) -> None:
        """Paso intermedio: el agente empezó algo y todavía no hay resultado."""
        self.emit(agent, "thinking", message, data=data)

    def output(self, agent: str, message: str, **data) -> None:
        """El agente terminó y entrega su resultado al siguiente."""
        self.emit(agent, "output", message, data=data)

    def error(self, agent: str, message: str, **data) -> None:
        self.emit(agent, "error", message, data=data)

    def ask(
        self,
        agent: str,
        checkpoint: str,
        question: str,
        *,
        draft: dict | None = None,
        options: tuple | list | None = None,
        timeout_s: float | None = None,
    ) -> dict:
        """Pausa el pipeline hasta que el usuario responda (o venza el plazo).

        Devuelve `{"action", "notes", "source"}`. Fuera de modo interactivo no
        pregunta nada y sigue de largo.
        """
        if not self.interactive:
            return {"action": "continue", "notes": "", "source": "auto"}

        self.emit(
            agent,
            "question",
            question,
            data={"draft": draft or {}},
            checkpoint=checkpoint,
            options=options or DEFAULT_OPTIONS,
        )

        deadline = time.monotonic() + (timeout_s or self._checkpoint_timeout_s)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.emit(
                    agent,
                    "answer",
                    "Sin respuesta a tiempo: el equipo sigue con su propio criterio.",
                    data={"source": "timeout"},
                    checkpoint=checkpoint,
                )
                return {"action": "continue", "notes": "", "source": "timeout"}

            try:
                reply = self._backend.pop_reply(self.trace_id, remaining)
            except Exception as exc:  # noqa: BLE001
                logger.warning("thoughts.reply_error", error=str(exc), checkpoint=checkpoint)
                return {"action": "continue", "notes": "", "source": "error"}

            if reply is None:
                continue
            # Respuesta rezagada de un checkpoint ya superado: descartar y seguir esperando.
            if reply.get("checkpoint") and reply["checkpoint"] != checkpoint:
                continue

            action = str(reply.get("action") or "continue").lower()
            if action not in _VALID_ACTIONS:
                action = "continue"
            notes = str(reply.get("notes") or "").strip()
            if action == "adjust" and not notes:
                action = "continue"

            self.emit(
                agent,
                "answer",
                notes or _ACTION_ECHO[action],
                data={"source": "user", "action": action},
                checkpoint=checkpoint,
            )
            if action == "cancel":
                raise RunCancelledByUser(checkpoint, notes)
            return {"action": action, "notes": notes, "source": "user"}


_ACTION_ECHO = {
    "continue": "El usuario aprobó continuar.",
    "adjust": "El usuario pidió ajustes.",
    "cancel": "El usuario detuvo el run.",
}


class NullThoughtStream:
    """Stream desactivado: mismas llamadas, sin efectos, para no ramificar el pipeline."""

    enabled = False
    interactive = False
    trace_id = ""

    def emit(self, *args, **kwargs) -> dict:
        return {}

    def think(self, *args, **kwargs) -> None:
        return None

    def output(self, *args, **kwargs) -> None:
        return None

    def error(self, *args, **kwargs) -> None:
        return None

    def ask(self, *args, **kwargs) -> dict:
        return {"action": "continue", "notes": "", "source": "auto"}


def _default_timeout() -> float:
    from gateway.app.core.settings import get_settings

    return float(get_settings().thoughts_checkpoint_timeout_seconds)


def build_stream(trace_id: str | None, *, interactive: bool = False):
    """Crea el stream del run, o un `NullThoughtStream` si no hay traza o está apagado."""
    from gateway.app.core.settings import get_settings

    if not trace_id or not get_settings().thoughts_enabled:
        return NullThoughtStream()
    return ThoughtStream(trace_id, interactive=interactive)


def read_events(trace_id: str, since: int = 0) -> list[dict]:
    """Eventos publicados a partir del índice `since` (para el polling del dashboard)."""
    try:
        return get_backend().read(trace_id, since)
    except Exception as exc:  # noqa: BLE001
        logger.warning("thoughts.read_error", error=str(exc), trace_id=trace_id)
        return []


def push_reply(trace_id: str, *, action: str, notes: str = "", checkpoint: str = "") -> dict:
    """Encola la respuesta del usuario para el agente que está esperando en un checkpoint."""
    clean = str(action or "").lower()
    if clean not in _VALID_ACTIONS:
        raise ValueError(f"action inválida: '{action}'. Usa continue | adjust | cancel.")
    reply = {"action": clean, "notes": notes.strip(), "checkpoint": checkpoint or ""}
    get_backend().push_reply(trace_id, reply)
    return reply
