"""TDD for hybrid deterministic scoring (trading-philosophy.md §3, §4.1).

Python recomputes the authoritative overall_score from each master's own
1-5 score using profile weights, derives BUY/HOLD/PASS, and flags divergence
from the LLM's advisory score.
"""
from __future__ import annotations

import math

import pytest

from app.core.scoring_config import (
    DEFAULT_SOURCE,
    PROFILE_WEIGHTS,
    REC_FALLBACK,
    SOURCE_QUALITY_SCREEN,
    SOURCE_THEME_SCAN,
)
from app.services.llm.scoring import (
    compute_overall_score,
    recommend,
    score_divergence,
)


class TestProfileWeights:
    def test_each_profile_sums_to_one(self):
        for source, weights in PROFILE_WEIGHTS.items():
            assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9), source

    def test_default_source_is_a_known_profile(self):
        assert DEFAULT_SOURCE in PROFILE_WEIGHTS


class TestComputeOverallScore:
    def test_compounder_weighted_average(self):
        scores = {"duan": 4.0, "buffett": 5.0, "munger": 3.0, "lilu": 4.0}
        # 0.25*4 + 0.30*5 + 0.20*3 + 0.25*4 = 1.0 + 1.5 + 0.6 + 1.0 = 4.1
        assert compute_overall_score(scores, SOURCE_QUALITY_SCREEN) == pytest.approx(4.1)

    def test_renormalizes_over_present_masters_when_one_missing(self):
        # lilu missing → renormalize remaining weights (0.25+0.30+0.20=0.75)
        scores = {"duan": 4.0, "buffett": 4.0, "munger": 4.0}
        # all 4.0 → weighted avg is 4.0 regardless of renormalization
        assert compute_overall_score(scores, SOURCE_QUALITY_SCREEN) == pytest.approx(4.0)

    def test_renormalization_actually_reweights(self):
        # buffett missing → weights renormalize over duan/munger/lilu
        scores = {"duan": 5.0, "munger": 1.0, "lilu": 3.0}
        w = {"duan": 0.25, "munger": 0.20, "lilu": 0.25}
        total = sum(w.values())
        expected = (5.0 * 0.25 + 1.0 * 0.20 + 3.0 * 0.25) / total
        assert compute_overall_score(scores, SOURCE_QUALITY_SCREEN) == pytest.approx(expected)

    def test_unknown_source_falls_back_to_default_profile(self):
        scores = {"duan": 3.0, "buffett": 3.0, "munger": 3.0, "lilu": 3.0}
        assert compute_overall_score(scores, "nonexistent") == pytest.approx(3.0)

    def test_ignores_scores_not_in_profile(self):
        # compounder profile has no "scarcity"; an stray key must be ignored,
        # not crash or skew the average.
        scores = {"duan": 4.0, "buffett": 4.0, "munger": 4.0, "lilu": 4.0, "scarcity": 1.0}
        assert compute_overall_score(scores, SOURCE_QUALITY_SCREEN) == pytest.approx(4.0)

    def test_theme_profile_includes_scarcity(self):
        scores = {"duan": 3.0, "buffett": 3.0, "munger": 3.0, "lilu": 3.0, "scarcity": 5.0}
        out = compute_overall_score(scores, SOURCE_THEME_SCAN)
        # scarcity at 5 pulls the all-3 baseline up
        assert out > 3.0

    def test_empty_scores_returns_none(self):
        assert compute_overall_score({}, SOURCE_QUALITY_SCREEN) is None


class TestSameSourceCap:
    """§4.1: masters sharing one advantage_source collapse to a single dimension
    (weight = max of group, score = mean of group), preventing double-counting."""

    SCORES = {"duan": 4.5, "buffett": 4.4, "munger": 3.5, "lilu": 4.0}

    def test_no_advantage_sources_means_no_cap(self):
        # baseline 4.145
        assert compute_overall_score(self.SCORES, SOURCE_QUALITY_SCREEN) == pytest.approx(4.145)
        assert compute_overall_score(
            self.SCORES, SOURCE_QUALITY_SCREEN, advantage_sources=None
        ) == pytest.approx(4.145)

    def test_same_source_collapses_duan_and_buffett(self):
        # duan & buffett both driven by the SAME advantage → collapse to one dim:
        # w = max(.25,.30)=.30, s = mean(4.5,4.4)=4.45; munger/lilu untouched.
        # renorm over .30+.20+.25=.75: (.30*4.45 + .20*3.5 + .25*4.0)/.75
        adv = {"duan": "regulatory_barrier", "buffett": "regulatory_barrier"}
        expected = (0.30 * 4.45 + 0.20 * 3.5 + 0.25 * 4.0) / 0.75
        assert compute_overall_score(
            self.SCORES, SOURCE_QUALITY_SCREEN, advantage_sources=adv
        ) == pytest.approx(expected)

    def test_collapse_lowers_score_vs_no_cap(self):
        adv = {"duan": "brand", "buffett": "brand"}
        capped = compute_overall_score(self.SCORES, SOURCE_QUALITY_SCREEN, advantage_sources=adv)
        uncapped = compute_overall_score(self.SCORES, SOURCE_QUALITY_SCREEN)
        assert capped < uncapped

    def test_different_sources_do_not_collapse(self):
        # duan & buffett tag DIFFERENT advantages → no collapse → baseline.
        adv = {"duan": "brand", "buffett": "cost_advantage"}
        assert compute_overall_score(
            self.SCORES, SOURCE_QUALITY_SCREEN, advantage_sources=adv
        ) == pytest.approx(4.145)

    def test_null_tag_master_not_grouped(self):
        # buffett tags an advantage but duan tags null → singletons, no collapse.
        adv = {"duan": None, "buffett": "brand"}
        assert compute_overall_score(
            self.SCORES, SOURCE_QUALITY_SCREEN, advantage_sources=adv
        ) == pytest.approx(4.145)

    def test_munger_lilu_never_collapse_even_if_tagged(self):
        # Risk/certainty axes are not advantage; a stray tag on them is ignored
        # because they carry no advantage_source in real runs. Here duan+buffett
        # share a source (collapse) while a tag on munger is its own singleton.
        adv = {"duan": "brand", "buffett": "brand", "munger": "brand"}
        # munger tagged 'brand' too → it WOULD join. Guard: only advantage
        # masters are eligible. Expected: only duan+buffett collapse; munger
        # stays independent (it is not an advantage master).
        expected = (0.30 * 4.45 + 0.20 * 3.5 + 0.25 * 4.0) / 0.75
        assert compute_overall_score(
            self.SCORES, SOURCE_QUALITY_SCREEN, advantage_sources=adv
        ) == pytest.approx(expected)

    def test_three_way_collapse_theme_profile(self):
        # theme profile: duan+buffett+scarcity all same source → one dim.
        scores = {"duan": 4.0, "buffett": 4.0, "munger": 3.0, "lilu": 3.0, "scarcity": 5.0}
        adv = {"duan": "chain_scarcity", "buffett": "chain_scarcity", "scarcity": "chain_scarcity"}
        out = compute_overall_score(scores, SOURCE_THEME_SCAN, advantage_sources=adv)
        # group weight = max(.22,.26,.24)=.26, score = mean(4,4,5)=4.333
        # dims: adv(.26@4.333), munger(.18@3), lilu(.10@3); renorm /.54
        expected = (0.26 * (13 / 3) + 0.18 * 3.0 + 0.10 * 3.0) / (0.26 + 0.18 + 0.10)
        assert out == pytest.approx(expected)


class TestRecommend:
    def test_buy_at_and_above_4(self):
        assert recommend(4.0) == "BUY"
        assert recommend(4.7) == "BUY"

    def test_hold_between_3_and_4(self):
        assert recommend(3.0) == "HOLD"
        assert recommend(3.9) == "HOLD"

    def test_pass_below_3(self):
        assert recommend(2.9) == REC_FALLBACK
        assert recommend(1.0) == REC_FALLBACK

    def test_none_score_is_pass(self):
        assert recommend(None) == REC_FALLBACK


class TestScoreDivergence:
    def test_within_epsilon_not_divergent(self):
        assert score_divergence(4.0, 4.2)["divergent"] is False

    def test_beyond_epsilon_divergent(self):
        d = score_divergence(4.0, 3.0)
        assert d["divergent"] is True
        assert d["delta"] == pytest.approx(1.0)

    def test_handles_none_llm_score(self):
        d = score_divergence(None, 4.0)
        assert d["divergent"] is False
        assert d["delta"] is None
