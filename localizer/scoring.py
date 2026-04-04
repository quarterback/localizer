"""Relevance scoring and filtering for procurement opportunities.

Scores each opportunity 0-100 based on configurable criteria and assigns
a priority tier: high, medium, low, or excluded.
"""

import re
from dataclasses import dataclass, field

# --- Default filter configuration ---

# Service keywords that indicate relevant consulting/advisory work (score boost)
INCLUDE_KEYWORDS = (
    "advisory",
    "strategic planning",
    "program design",
    "capacity building",
    "process improvement",
    "service design",
    "technology assessment",
    "feasibility study",
    "organizational assessment",
    "digital services",
    "digital transformation",
    "consulting",
    "evaluation",
    "stakeholder engagement",
    "community engagement",
    "equity",
    "data strategy",
    "change management",
    "project management",
    "technical assistance",
    "needs assessment",
    "gap analysis",
    "performance",
    "modernization",
    "user research",
    "delivery",
)

# Auto-exclude: hard-exclude if title/description matches these
EXCLUDE_KEYWORDS = (
    "construction",
    "janitorial",
    "landscaping",
    "security guard",
    "security services",
    "food service",
    "food preparation",
    "catering",
    "maintenance",
    "asbestos",
    "hvac",
    "paving",
    "roofing",
    "plumbing",
    "electrical contractor",
    "demolition",
    "excavation",
    "concrete",
    "fencing",
    "towing",
    "hauling",
    "pest control",
    "custodial",
    "mowing",
    "snow removal",
)

# Solicitation types to include vs exclude
INCLUDE_TYPES = {"RFP", "RFQ", "RFI", "RFS", "SOQ", "PSS", "other"}
EXCLUDE_TYPES = {"IFB", "ITB"}

# Source priority (higher = more relevant to you)
SOURCE_PRIORITY = {
    "portland": 5,
    "multnomah": 4,
    "metro": 3,
    "trimet": 3,
    "port": 2,
    "oregonbuys": 1,
}

# Minimum contract value (0 means include everything including unlisted)
MIN_VALUE = 5000


@dataclass
class ScoredRFP:
    """An RFP with relevance scoring metadata."""
    rfp: dict
    score: int = 0
    priority: str = "low"  # high, medium, low, excluded
    matched_keywords: list[str] = field(default_factory=list)
    exclude_reason: str | None = None


def parse_dollar_amount(text: str | None) -> int | None:
    """Extract a dollar amount from text like '$50,000' or '$150K' or '50000'.

    Returns None if no amount found (which means "unknown", not "zero").
    """
    if not text:
        return None
    text = text.strip().replace(",", "").replace("$", "")
    # Handle K/M suffixes
    m = re.search(r'(\d+(?:\.\d+)?)\s*([kmKM])?', text)
    if not m:
        return None
    amount = float(m.group(1))
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        amount *= 1000
    elif suffix == "M":
        amount *= 1_000_000
    return int(amount)


def score_rfp(rfp: dict) -> ScoredRFP:
    """Score a single RFP based on relevance criteria.

    Returns a ScoredRFP with score (0-100), priority tier, and match details.
    """
    result = ScoredRFP(rfp=rfp)
    text = _searchable_text(rfp)
    score = 0

    # --- Check hard exclusions first ---

    # Excluded solicitation types (IFB, ITB = pure bid, not consulting)
    sol_type = (rfp.get("solicitation_type") or "other").upper()
    if sol_type in EXCLUDE_TYPES:
        result.score = 0
        result.priority = "excluded"
        result.exclude_reason = f"Excluded type: {sol_type}"
        return result

    # Excluded keywords
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            result.score = 0
            result.priority = "excluded"
            result.exclude_reason = f"Excluded keyword: {kw}"
            return result

    # Contract value check (only exclude if value is known AND below minimum)
    value = parse_dollar_amount(rfp.get("estimated_value"))
    if value is not None and value < MIN_VALUE:
        result.score = 0
        result.priority = "excluded"
        result.exclude_reason = f"Below ${MIN_VALUE:,} minimum (${value:,})"
        return result

    # --- Positive scoring ---

    # Solicitation type (max 20 points)
    if sol_type == "RFP":
        score += 20
    elif sol_type in ("RFQ", "SOQ"):
        score += 15
    elif sol_type == "RFI":
        score += 12
    elif sol_type in ("RFS", "PSS"):
        score += 18
    else:
        score += 5  # unknown type, still include

    # Source priority (max 25 points)
    source = rfp.get("source", "")
    source_score = SOURCE_PRIORITY.get(source, 0)
    score += source_score * 5  # 5-25 points

    # Keyword matches (max 40 points)
    matched = []
    for kw in INCLUDE_KEYWORDS:
        if kw in text:
            matched.append(kw)
    if matched:
        # Diminishing returns: first few matches worth more
        kw_score = min(40, len(matched) * 10)
        score += kw_score
    result.matched_keywords = matched

    # Contract value bonus (max 15 points)
    if value is not None:
        if 5_000 <= value <= 500_000:
            score += 15  # Sweet spot
        elif value > 500_000:
            score += 5  # Large but still possible as subcontractor
    else:
        score += 8  # Unknown value = probably fine, slight bonus for not being excluded

    # Cap at 100
    result.score = min(100, score)

    # Assign priority tier
    if result.score >= 60:
        result.priority = "high"
    elif result.score >= 35:
        result.priority = "medium"
    else:
        result.priority = "low"

    return result


def score_rfps(rfps: list[dict]) -> list[ScoredRFP]:
    """Score and sort a list of RFPs by relevance. Highest score first."""
    scored = [score_rfp(r) for r in rfps]
    scored.sort(key=lambda s: (-_priority_rank(s.priority), -s.score))
    return scored


def filter_rfps(rfps: list[dict], min_priority: str = "low") -> list[ScoredRFP]:
    """Score RFPs and filter to only those at or above min_priority.

    Args:
        rfps: Raw RFP dicts from the database.
        min_priority: Minimum priority to include. One of: high, medium, low.
                      "excluded" items are always filtered out.
    """
    scored = score_rfps(rfps)
    min_rank = _priority_rank(min_priority)
    return [s for s in scored if _priority_rank(s.priority) >= min_rank]


def _searchable_text(rfp: dict) -> str:
    """Combine title + description + category into lowercase searchable text."""
    parts = [
        rfp.get("title") or "",
        rfp.get("description") or "",
        rfp.get("category") or "",
    ]
    return " ".join(parts).lower()


def _priority_rank(priority: str) -> int:
    return {"high": 3, "medium": 2, "low": 1, "excluded": 0}.get(priority, 0)
