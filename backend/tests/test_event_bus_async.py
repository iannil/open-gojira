"""Tests for async EventBus dispatch."""

import threading
import time

from app.core.events import bus, BaseEvent, shutdown_executor


class _TestEvent(BaseEvent):
    """Test event type."""
    pass


def test_emit_async_does_not_block():
    """emit_async should return before slow handlers complete."""
    slow_done = threading.Event()
    handler_thread_ids = []

    def slow_handler(event):
        time.sleep(0.1)
        handler_thread_ids.append(threading.current_thread().ident)
        slow_done.set()

    bus.subscribe(_TestEvent, slow_handler)
    try:
        start = time.monotonic()
        bus.emit_async(_TestEvent())
        elapsed = time.monotonic() - start
        # Should return immediately, not wait 0.1s
        assert elapsed < 0.05, f"emit_async blocked for {elapsed:.3f}s"
        # Wait for handler to finish
        assert slow_done.wait(timeout=1.0), "Handler did not complete"
        # Handler ran in a different thread
        assert handler_thread_ids[-1] != threading.current_thread().ident
    finally:
        # Cleanup: remove handler from registry
        with bus._lock:
            bus._handlers.get(_TestEvent, []).remove(slow_handler)
        shutdown_executor()


def test_emit_sync_still_blocks():
    """emit (sync) should still block until handlers complete."""
    done = threading.Event()

    def handler(event):
        done.set()

    bus.subscribe(_TestEvent, handler)
    try:
        bus.emit(_TestEvent())
        assert done.is_set()
    finally:
        with bus._lock:
            bus._handlers.get(_TestEvent, []).remove(handler)
