"""C2: plan_runner business_pattern scan scope — filter stocks by BusinessPattern."""

from app.models.business_pattern import BusinessPattern
from app.models.plan import Plan
from app.models.stock import Stock


def _make_plan(db_session, scope_json: str) -> Plan:
    p = Plan(
        name="t", slug="t-bp-scope", status="active",
        strategy_composition_json='{"strategy_ids": [], "logic": "AND"}',
        scan_scope_json=scope_json,
        schedule_cron="0 18 * * 1-5",
        is_builtin=False,
    )
    db_session.add(p)
    db_session.flush()
    return p


class TestBusinessPatternScope:
    def test_returns_stocks_matching_pattern(self, db_session):
        from app.services.plan_runner import _resolve_scope
        bp1 = BusinessPattern(name="煤化工", power_tier_baseline=2, is_builtin=True)
        bp2 = BusinessPattern(name="药店零售", power_tier_baseline=2, is_builtin=True)
        db_session.add_all([bp1, bp2])
        db_session.flush()

        db_session.add(Stock(code="A", name="A", business_pattern_id=bp1.id))
        db_session.add(Stock(code="B", name="B", business_pattern_id=bp1.id))
        db_session.add(Stock(code="C", name="C", business_pattern_id=bp2.id))
        db_session.add(Stock(code="D", name="D", business_pattern_id=None))
        db_session.flush()

        plan = _make_plan(db_session, f'{{"type": "business_pattern", "values": ["{bp1.id}"]}}')
        codes = _resolve_scope(db_session, plan)
        assert set(codes) == {"A", "B"}

    def test_multiple_patterns_union(self, db_session):
        from app.services.plan_runner import _resolve_scope
        bp1 = BusinessPattern(name="煤化工", power_tier_baseline=2, is_builtin=True)
        bp2 = BusinessPattern(name="药店零售", power_tier_baseline=2, is_builtin=True)
        db_session.add_all([bp1, bp2])
        db_session.flush()

        db_session.add(Stock(code="A", name="A", business_pattern_id=bp1.id))
        db_session.add(Stock(code="C", name="C", business_pattern_id=bp2.id))
        db_session.flush()

        plan = _make_plan(
            db_session,
            f'{{"type": "business_pattern", "values": ["{bp1.id}", "{bp2.id}"]}}',
        )
        codes = set(_resolve_scope(db_session, plan))
        assert codes == {"A", "C"}

    def test_empty_when_no_stocks_match(self, db_session):
        from app.services.plan_runner import _resolve_scope
        bp1 = BusinessPattern(name="煤化工", power_tier_baseline=2, is_builtin=True)
        db_session.add(bp1)
        db_session.flush()
        # Stock with no pattern
        db_session.add(Stock(code="X", name="X", business_pattern_id=None))
        db_session.flush()

        plan = _make_plan(db_session, f'{{"type": "business_pattern", "values": ["{bp1.id}"]}}')
        assert _resolve_scope(db_session, plan) == []

    def test_invalid_id_raises(self, db_session):
        from app.services.plan_runner import _resolve_scope
        import pytest
        plan = _make_plan(
            db_session,
            '{"type": "business_pattern", "values": ["not_a_number"]}',
        )
        with pytest.raises(ValueError):
            _resolve_scope(db_session, plan)
