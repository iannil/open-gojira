"""Structured logging, lifecycle tracking, and request tracing.

Configures structlog for JSON output with trace_id/span_id propagation.
Provides a LifecycleTracker decorator for automatic function instrumentation.
Supports nested spans, parameter serialization, and file-based log rotation.
"""

import contextvars
import functools
import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import structlog

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_OBS_LEVEL = os.environ.get("OBSERVABILITY_LEVEL", "full").lower()
_OBS_EXCLUDE: list[str] = [
    p.strip()
    for p in os.environ.get("OBSERVABILITY_EXCLUDE", "").split(",")
    if p.strip()
]
_OBS_LOG_DIR = Path(os.environ.get("OBSERVABILITY_LOG_DIR", "logs/observability"))
_OBS_MAX_DEPTH = 4
_OBS_MAX_STR_LEN = 500

# ---------------------------------------------------------------------------
# Context variables for trace propagation
# ---------------------------------------------------------------------------

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)
span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "span_id", default=""
)
_parent_span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "parent_span_id", default=""
)

# Span stack for nesting
_span_stack: contextvars.ContextVar[list[str]] = contextvars.ContextVar(
    "span_stack", default=[]
)


def _generate_id() -> str:
    return uuid.uuid4().hex[:16]


def set_trace_id(tid: str) -> None:
    trace_id_var.set(tid)


def set_span_id(sid: str) -> None:
    span_id_var.set(sid)


def _push_span(sid: str) -> None:
    stack = _span_stack.get([])
    stack.append(sid)
    _span_stack.set(stack)


def _pop_span() -> str:
    stack = _span_stack.get([])
    if stack:
        sid = stack.pop()
        _span_stack.set(stack)
        return sid
    return ""


def _current_parent_id() -> str:
    stack = _span_stack.get([])
    return stack[-1] if stack else ""


# ---------------------------------------------------------------------------
# Observability level helpers
# ---------------------------------------------------------------------------

def observability_level() -> str:
    return _OBS_LEVEL


def should_observe(module_name: str = "") -> bool:
    if _OBS_LEVEL == "off":
        return False
    for pattern in _OBS_EXCLUDE:
        if pattern in module_name:
            return False
    return True


def is_compact() -> bool:
    return _OBS_LEVEL == "compact"


# ---------------------------------------------------------------------------
# Safe serialization
# ---------------------------------------------------------------------------

def _safe_serialize(obj: Any, depth: int = 0) -> Any:
    if depth > _OBS_MAX_DEPTH:
        return "<max_depth>"

    if obj is None or isinstance(obj, (bool, int, float)):
        return obj

    if isinstance(obj, str):
        return obj[:_OBS_MAX_STR_LEN] if len(obj) > _OBS_MAX_STR_LEN else obj

    if isinstance(obj, bytes):
        return f"<bytes:{len(obj)}>"

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, dict):
        return {
            str(k)[:_OBS_MAX_STR_LEN]: _safe_serialize(v, depth + 1)
            for k, v in list(obj.items())[:50]
        }

    if isinstance(obj, (list, tuple, set, frozenset)):
        items = list(obj)[:50]
        return [_safe_serialize(item, depth + 1) for item in items]

    # SQLAlchemy Session
    type_name = type(obj).__name__
    module = type(obj).__module__ or ""
    if "sqlalchemy" in module and "Session" in type_name:
        return "<Session>"

    # SQLAlchemy Model instances
    if hasattr(obj, "__tablename__") and hasattr(obj, "__dict__"):
        pk = getattr(obj, "id", "?")
        return f"<Model:{type_name}:{pk}>"

    # Pydantic models
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        try:
            return _safe_serialize(obj.model_dump(), depth + 1)
        except Exception:
            return f"<{type_name}>"

    # FastAPI Request/Response
    if type_name in ("Request", "Response"):
        return f"<{type_name}>"

    # Callable / functions
    if callable(obj):
        return f"<func:{getattr(obj, '__qualname__', type_name)}>"

    # Fallback — try to stringify, truncate
    try:
        s = str(obj)
        return s[:_OBS_MAX_STR_LEN] if len(s) > _OBS_MAX_STR_LEN else s
    except Exception:
        return f"<{type_name}>"


def _serialize_args(
    args: tuple, kwargs: dict, func: Callable, compact_mode: bool
) -> dict:
    if compact_mode or is_compact():
        return {
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()),
        }

    import inspect

    sig = inspect.signature(func)
    params = list(sig.parameters.keys())

    serialized: dict[str, Any] = {}
    for i, arg in enumerate(args):
        name = params[i] if i < len(params) else f"arg{i}"
        serialized[name] = _safe_serialize(arg)

    for k, v in kwargs.items():
        serialized[k] = _safe_serialize(v)

    return serialized


def _serialize_return(result: Any, compact_mode: bool) -> dict:
    if compact_mode or is_compact():
        type_name = type(result).__name__
        if isinstance(result, (list, tuple, set)):
            return {"return_type": type_name, "return_count": len(result)}
        if isinstance(result, dict):
            return {
                "return_type": "dict",
                "return_keys": list(result.keys())[:20],
            }
        return {"return_type": type_name}

    serialized = _safe_serialize(result)
    type_name = type(result).__name__

    summary: dict[str, Any] = {"return_type": type_name}
    if isinstance(result, dict):
        summary["return_keys"] = list(result.keys())[:20]
    elif isinstance(result, (list, tuple)):
        summary["return_count"] = len(result)

    summary["return_value"] = serialized
    return summary


# ---------------------------------------------------------------------------
# Structlog configuration
# ---------------------------------------------------------------------------

def _add_context_vars(logger, method, event_dict):
    tid = trace_id_var.get("")
    if tid:
        event_dict["trace_id"] = tid
    sid = span_id_var.get("")
    if sid:
        event_dict["span_id"] = sid
    pid = _parent_span_id_var.get("")
    if pid:
        event_dict["parent_span_id"] = pid
    return event_dict


_file_handler: logging.handlers.TimedRotatingFileHandler | None = None


def _setup_file_logging() -> None:
    global _file_handler
    if _file_handler is not None:
        return

    _OBS_LOG_DIR.mkdir(parents=True, exist_ok=True)

    import datetime as _dt

    today = _dt.date.today().isoformat()
    log_file = _OBS_LOG_DIR / f"obs-{today}.jsonl"

    _file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    _file_handler.suffix = "obs-%Y-%m-%d.jsonl"
    _file_handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger("obs")
    root.setLevel(logging.DEBUG)
    root.addHandler(_file_handler)


def configure_logging() -> None:
    """Configure structlog for JSON structured logging with file output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_context_vars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    if _OBS_LEVEL != "off":
        _setup_file_logging()


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger bound to the given module name."""
    return structlog.get_logger(name)


def _emit_obs_log(event_dict: dict) -> None:
    """Write a structured observation line to the obs log file."""
    if _file_handler is None or _OBS_LEVEL == "off":
        return
    try:
        import datetime as _dt

        record = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), **event_dict}

        tid = trace_id_var.get("")
        if tid and "trace_id" not in record:
            record["trace_id"] = tid

        line = json.dumps(record, ensure_ascii=False, default=str)
        _file_handler.emit(logging.LogRecord(
            name="obs", level=logging.DEBUG, pathname="", lineno=0,
            msg=line, args=(), exc_info=None,
        ))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# LifecycleTracker decorator
# ---------------------------------------------------------------------------

class LifecycleTracker:
    """Decorator for automatic function instrumentation with nested spans.

    Logs function enter/exit with args, return value, duration, and exceptions.
    Supports nested calls via contextvar span stack.
    """

    def __init__(self, func: Callable = None, *, span_name: str = "", compact: bool = False):
        self._func = func
        self._span_name = span_name
        self._compact = compact
        if func is not None:
            functools.update_wrapper(self, func)

    def __call__(self, *args, **kwargs):
        if self._func is None:
            self._func = args[0]
            functools.update_wrapper(self, self._func)
            return self
        return self._execute(self._func, args, kwargs)

    def __get__(self, obj, objtype=None):
        return functools.partial(self.__call__, obj)

    def _execute(self, func, args, kwargs):
        if not should_observe(func.__module__):
            return func(*args, **kwargs)

        name = self._span_name or func.__qualname__
        sid = _generate_id()
        parent_id = _current_parent_id()

        set_span_id(sid)
        _parent_span_id_var.set(parent_id)
        _push_span(sid)

        # Filter out self and db: Session from args for cleaner logs
        serialized_args = _serialize_args(args, kwargs, func, self._compact)

        log = get_logger(func.__module__)

        # Emit Function_Start
        start_event: dict[str, Any] = {
            "span_id": sid,
            "parent_span_id": parent_id,
            "function": name,
            "args": serialized_args,
        }
        log.info("Function_Start", **start_event)
        _emit_obs_log({"event": "Function_Start", **start_event})

        start = time.monotonic()
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.monotonic() - start) * 1000

            return_info = _serialize_return(result, self._compact)

            end_event: dict[str, Any] = {
                "span_id": sid,
                "parent_span_id": parent_id,
                "function": name,
                "duration_ms": round(duration_ms, 2),
                **return_info,
            }
            log.info("Function_End", **end_event)
            _emit_obs_log({"event": "Function_End", **end_event})

            return result
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000

            error_event: dict[str, Any] = {
                "span_id": sid,
                "parent_span_id": parent_id,
                "function": name,
                "duration_ms": round(duration_ms, 2),
                "error_type": type(e).__name__,
                "error_message": str(e)[:1000],
            }
            log.error("Error", **error_event)
            _emit_obs_log({"event": "Error", **error_event})
            raise
        finally:
            _pop_span()
            set_span_id(parent_id)
            _parent_span_id_var.set(
                _span_stack.get([])[-1] if _span_stack.get([]) else ""
            )


def track_lifecycle(func: Callable = None, *, span_name: str = "", compact: bool = False):
    """Convenience decorator. Use as @track_lifecycle or @track_lifecycle(span_name="...")."""
    tracker = LifecycleTracker(func, span_name=span_name, compact=compact)
    if func is not None:
        return tracker
    return tracker
