"""Tests for the relevance scoring and filtering engine."""

import pytest

from localizer.scoring import (
    score_rfp, score_rfps, filter_rfps, parse_dollar_amount, ScoredRFP,
)


class TestParseDollarAmount:
    def test_basic_amounts(self):
        assert parse_dollar_amount("$50,000") == 50000
        assert parse_dollar_amount("$150K") == 150000
        assert parse_dollar_amount("$2.5M") == 2500000
        assert parse_dollar_amount("50000") == 50000
        assert parse_dollar_amount("$75k") == 75000

    def test_none_and_empty(self):
        assert parse_dollar_amount(None) is None
        assert parse_dollar_amount("") is None
        assert parse_dollar_amount("TBD") is None
        assert parse_dollar_amount("N/A") is None


class TestScoring:
    def test_high_priority_advisory_rfp(self):
        """RFP for advisory services from Portland should score high."""
        result = score_rfp({
            "source": "portland",
            "title": "RFP: Strategic Planning and Advisory Services",
            "solicitation_type": "RFP",
            "description": "Seeking consultant for organizational assessment and process improvement",
            "estimated_value": "$150,000",
        })
        assert result.priority == "high"
        assert result.score >= 60
        assert len(result.matched_keywords) >= 2
        assert "advisory" in result.matched_keywords or "strategic planning" in result.matched_keywords

    def test_construction_excluded(self):
        """Construction projects should be excluded."""
        result = score_rfp({
            "source": "portland",
            "title": "Construction of New Community Center",
            "solicitation_type": "RFP",
        })
        assert result.priority == "excluded"
        assert result.score == 0
        assert "construction" in result.exclude_reason.lower()

    def test_janitorial_excluded(self):
        result = score_rfp({
            "source": "multnomah",
            "title": "Janitorial Services for County Buildings",
            "solicitation_type": "RFP",
        })
        assert result.priority == "excluded"

    def test_ifb_excluded(self):
        """IFB type should be auto-excluded."""
        result = score_rfp({
            "source": "portland",
            "title": "Digital Services Modernization",
            "solicitation_type": "IFB",
        })
        assert result.priority == "excluded"
        assert "type" in result.exclude_reason.lower()

    def test_itb_excluded(self):
        result = score_rfp({
            "source": "portland",
            "title": "Office Supplies",
            "solicitation_type": "ITB",
        })
        assert result.priority == "excluded"

    def test_below_minimum_value_excluded(self):
        result = score_rfp({
            "source": "portland",
            "title": "Small Advisory Engagement",
            "solicitation_type": "RFP",
            "estimated_value": "$2,000",
        })
        assert result.priority == "excluded"

    def test_unknown_value_not_excluded(self):
        """If no value listed, should NOT be excluded."""
        result = score_rfp({
            "source": "portland",
            "title": "Technology Assessment Project",
            "solicitation_type": "RFP",
            "estimated_value": None,
        })
        assert result.priority != "excluded"
        assert result.score > 0

    def test_source_priority_portland_highest(self):
        """Portland should score higher than oregonbuys for same opportunity."""
        portland = score_rfp({
            "source": "portland",
            "title": "Generic Consulting Project",
            "solicitation_type": "RFP",
        })
        oregon = score_rfp({
            "source": "oregonbuys",
            "title": "Generic Consulting Project",
            "solicitation_type": "RFP",
        })
        assert portland.score > oregon.score

    def test_keyword_matching(self):
        result = score_rfp({
            "source": "metro",
            "title": "Feasibility Study for Digital Services",
            "solicitation_type": "RFP",
            "description": "Capacity building and service design engagement",
        })
        assert "feasibility study" in result.matched_keywords
        assert "digital services" in result.matched_keywords
        assert "capacity building" in result.matched_keywords
        assert "service design" in result.matched_keywords

    def test_medium_priority(self):
        """Something with fewer matches should land in medium."""
        result = score_rfp({
            "source": "oregonbuys",
            "title": "General Office Equipment RFP",
            "solicitation_type": "RFP",
        })
        assert result.priority in ("medium", "low")

    def test_rfq_scores(self):
        result = score_rfp({
            "source": "portland",
            "title": "RFQ: Program Design Consultant",
            "solicitation_type": "RFQ",
        })
        assert result.priority in ("high", "medium")
        assert result.score > 0

    def test_description_searched(self):
        """Keywords in description should match too."""
        result = score_rfp({
            "source": "portland",
            "title": "Vendor Engagement",
            "solicitation_type": "RFP",
            "description": "Technology assessment and digital transformation consulting",
        })
        assert "technology assessment" in result.matched_keywords

    def test_max_score_100(self):
        """Score should cap at 100."""
        result = score_rfp({
            "source": "portland",
            "title": "RFP Advisory Strategic Planning Program Design Capacity Building",
            "solicitation_type": "RFP",
            "description": "Service design technology assessment feasibility study organizational assessment digital services process improvement evaluation change management modernization",
            "estimated_value": "$100,000",
        })
        assert result.score <= 100


class TestFilterRfps:
    def _make_rfps(self):
        return [
            {"source": "portland", "title": "RFP: Advisory Services for Digital Transformation",
             "solicitation_type": "RFP", "description": "Strategic planning and service design"},
            {"source": "portland", "title": "Construction of Parking Garage",
             "solicitation_type": "IFB"},
            {"source": "multnomah", "title": "Janitorial Services Contract",
             "solicitation_type": "RFP"},
            {"source": "oregonbuys", "title": "General Office Equipment",
             "solicitation_type": "RFP"},
        ]

    def test_filter_excludes_construction_and_janitorial(self):
        scored = filter_rfps(self._make_rfps(), min_priority="low")
        titles = [s.rfp["title"] for s in scored]
        assert "Construction of Parking Garage" not in titles
        assert "Janitorial Services Contract" not in titles

    def test_filter_high_only(self):
        scored = filter_rfps(self._make_rfps(), min_priority="high")
        assert all(s.priority == "high" for s in scored)

    def test_sorted_by_score(self):
        scored = filter_rfps(self._make_rfps(), min_priority="low")
        for i in range(len(scored) - 1):
            assert scored[i].score >= scored[i + 1].score

    def test_score_rfps_includes_all(self):
        """score_rfps returns everything including excluded."""
        all_scored = score_rfps(self._make_rfps())
        assert len(all_scored) == 4
        assert any(s.priority == "excluded" for s in all_scored)
