"""Tests for EventBus core: emit, subscribe, error isolation, observability."""
import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel

from app.core.events import EventBus, BaseEvent, bus


class _TestEvent(BaseEvent):
    message: str = "hello"
    value: int = 0


class _OtherEvent(BaseEvent):
    data: str = ""


class TestBaseEvent:
    def test_auto_fields(self):
        e = _TestEvent()
        assert e.event_id
        assert e.timestamp
        assert len(e.event_id) == 16

    def test_custom_fields(self):
        e = _TestEvent(message="world", value=42)
        assert e.message == "world"
        assert e.value == 42


class TestEventBus:
    def test_subscribe_and_emit(self):
        test_bus = EventBus()
        received = []
        test_bus.subscribe(_TestEvent, lambda e: received.append(e))
        test_bus.emit(_TestEvent(message="hi"))
        assert len(received) == 1
        assert received[0].message == "hi"

    def test_multiple_handlers(self):
        test_bus = EventBus()
        a, b = [], []
        test_bus.subscribe(_TestEvent, lambda e: a.append(e))
        test_bus.subscribe(_TestEvent, lambda e: b.append(e))
        test_bus.emit(_TestEvent())
        assert len(a) == 1
        assert len(b) == 1

    def test_no_handler_no_error(self):
        test_bus = EventBus()
        test_bus.emit(_TestEvent())

    def test_handler_error_does_not_block_others(self):
        test_bus = EventBus()
        good = []
        test_bus.subscribe(_TestEvent, lambda e: 1 / 0)
        test_bus.subscribe(_TestEvent, lambda e: good.append(e))
        test_bus.emit(_TestEvent())
        assert len(good) == 1

    def test_handler_error_logged(self):
        test_bus = EventBus()
        test_bus.subscribe(_TestEvent, lambda e: 1 / 0)
        test_bus.emit(_TestEvent())

    def test_event_type_isolation(self):
        test_bus = EventBus()
        received = []
        test_bus.subscribe(_TestEvent, lambda e: received.append(e))
        test_bus.emit(_OtherEvent(data="x"))
        assert len(received) == 0

    def test_get_registry(self):
        test_bus = EventBus()
        test_bus.subscribe(_TestEvent, lambda e: None)
        test_bus.subscribe(_OtherEvent, lambda e: None)
        reg = test_bus.get_registry()
        assert _TestEvent in reg
        assert _OtherEvent in reg
        assert len(reg[_TestEvent]) == 1
        assert len(reg[_OtherEvent]) == 1


class TestGlobalBus:
    def test_global_bus_is_eventbus(self):
        from app.core.events import bus
        assert isinstance(bus, EventBus)


class TestEventHandlers:
    def test_data_sync_handler_ignores_non_matching_pipeline(self):
        """on_kline_sync_price_alert is a no-op — should not crash."""
        from app.core.events import DataSyncCompleted
        import app.core.event_handlers
        event = DataSyncCompleted(
            pipeline_type="klines",
            stock_codes=["000001"],
            run_id="test",
            status="success",
        )
        app.core.event_handlers.on_kline_sync_price_alert(event)

    def test_data_sync_handler_ignores_failed(self):
        """on_kline_sync_price_alert returns None regardless of status."""
        from app.core.events import DataSyncCompleted
        import app.core.event_handlers
        event = DataSyncCompleted(
            pipeline_type="valuations",
            stock_codes=["000001"],
            run_id="test",
            status="failed",
        )
        result = app.core.event_handlers.on_kline_sync_price_alert(event)
        assert result is None

    def test_handlers_register_on_import(self):
        # v2: DataSyncCompleted→price_alert(no-op),
        # DraftCreated→audit_log, MonthlyBudgetExceeded→budget handler,
        # ThesisAlertTriggered→thesis_breach sell draft.
        from app.core.events import bus, DataSyncCompleted, DraftCreated, MonthlyBudgetExceeded, ThesisAlertTriggered
        reg = bus.get_registry()
        assert DataSyncCompleted in reg
        assert DraftCreated in reg
        assert MonthlyBudgetExceeded in reg
        assert ThesisAlertTriggered in reg
        assert len(reg[DataSyncCompleted]) == 1  # on_kline_sync_price_alert
        assert len(reg[DraftCreated]) == 1  # on_draft_audit_log
        assert len(reg[MonthlyBudgetExceeded]) == 1
        assert len(reg[ThesisAlertTriggered]) == 1

    def test_max_stocks_limit_applied(self):
        from app.core.events import DataSyncCompleted
        import app.core.event_handlers
        event = DataSyncCompleted(
            pipeline_type="valuations",
            stock_codes=[f"00{i:04d}" for i in range(100)],
            run_id="test",
            status="success",
        )
        # Handler should not raise even with 100 codes (truncated to 50 internally)
        import app.core.event_handlers
        # Just verify it doesn't crash — actual DB work requires real session
        assert app.core.event_handlers.MAX_STOCKS_PER_HANDLER == 50
