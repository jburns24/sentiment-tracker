"""Context dataclass for rendering feedback reports.

This module defines `ReportContext`, a typed container that holds all
values expected by the master Jinja2 template located in
`src/reporting/templates/report.md.j2`.

The separation between *context building* and *template rendering*
enables:
    • Clear contracts between aggregation/analysis logic and Jinja2.
    • Easier unit-testing of business logic without touching template
      strings.
    • Future extension (e.g., HTML or JSON reports) by reusing the same
      context object.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime as _dt
from datetime import timezone as _tz
from typing import Any, Dict, List

from src.analysis.anonymize import anonymize_quotes
from src.analysis.themes import extract_themes
from src.reporting import config
from src.reporting.models import ProcessedFeedback

__all__ = [
    "Stats",
    "ReportContext",
]


@dataclass(slots=True)
class Stats:
    """Basic participation statistics displayed in the report."""

    submitted: int
    total_participants: int
    low_participation: bool = False

    def to_dict(self) -> Dict[str, Any]:  # noqa: D401 – simple helper
        """Return a *plain* ``dict`` representation suitable for Jinja."""
        return asdict(self)


@dataclass(slots=True)
class ReportContext:
    """Container with all fields used by the Slack report template."""

    # Header & meta
    session_id: str
    date: str  # ISO-8601 date string (UTC)

    # Participation & sentiment
    stats: Stats
    emoji_bar: str
    sentiment_counts: Dict[str, int]

    # Analysis outputs
    themes: List[str] = field(default_factory=list)
    bullets_well: List[str] = field(default_factory=list)
    bullets_improve: List[str] = field(default_factory=list)

    # Raw anonymized comments (full list)
    all_items: List[str] = field(default_factory=list)

    # Misc / versioning
    version: str = "1"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:  # noqa: D401 – simple helper
        """Return a *plain* ``dict`` (recursively) for Jinja rendering."""
        return asdict(self)

    # Alias for convenience (e.g. template kwargs)
    __call__ = to_dict


# ---------------------------------------------------------------------------
# Local helper functions (kept here to avoid circular import with render)
# ---------------------------------------------------------------------------
def _emoji_bar(counts: dict[str, int], max_emoji: int = 20) -> str:  # pragma: no cover
    """Return a string bar of emojis based on *counts*.

    Positive → 😊, Neutral → 😐, Negative → 🙁.  Limit total length to
    *max_emoji*.
    """

    pos = counts.get("positive", 0)
    neu = counts.get("neutral", 0)
    neg = counts.get("negative", 0)
    total = pos + neu + neg or 1

    scale = max_emoji / total
    pos_e = "😊" * max(1 if pos else 0, round(pos * scale))
    neu_e = "😐" * max(1 if neu else 0, round(neu * scale))
    neg_e = "🙁" * max(1 if neg else 0, round(neg * scale))
    return pos_e + neu_e + neg_e


def _split_highlights(items: List[str], *, max_each: int = config.MAX_BULLETS_EACH):
    """Return (well, improve) bullet lists extracted from structured items."""

    well: List[str] = []
    improve: List[str] = []

    for it in items:
        # naive parse of "well=..., improve=..." pattern
        if "well=" in it:
            _, after = it.split("well=", 1)
            txt = after.split(",", 1)[0].strip()
            well.append(f"• {txt}")
        if "improve=" in it:
            _, after = it.split("improve=", 1)
            txt = after.strip()
            improve.append(f"• {txt}")

    return well[:max_each], improve[:max_each]


# ---------------------------------------------------------------------------
# Conversion helper
# ---------------------------------------------------------------------------
def build_report_context(processed: ProcessedFeedback) -> ReportContext:  # noqa: WPS231
    """Convert ``ProcessedFeedback`` into :class:`ReportContext`.

    The function is *pure* – it does not mutate *processed* and will
    swallow non-critical errors (anonymization/theme extraction) so that
    downstream rendering always succeeds.
    """

    # ------------------------------------------------------------------
    # Pre-processing – anonymize & analyse
    # ------------------------------------------------------------------
    try:
        anonymized_items = anonymize_quotes(processed.all_items)
    except Exception as exc:  # noqa: BLE001 – robustness
        # Log via root logger; keep import local to avoid circular
        logging.getLogger(__name__).warning("Anonymization failed: %s", exc)
        anonymized_items = processed.all_items

    # Cap comments to avoid overly long Slack messages
    anonymized_items = anonymized_items[: config.MAX_COMMENTS]

    try:
        themes = extract_themes(anonymized_items)[: config.MAX_THEMES]
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("Theme extraction failed: %s", exc)
        themes = []

    # Highlights
    bullets_well, bullets_improve = _split_highlights(
        anonymized_items, max_each=config.MAX_BULLETS_EACH
    )

    # Participation stats packaging
    stats = Stats(
        submitted=processed.stats.get("submitted", 0),
        total_participants=processed.stats.get("total_participants", 0),
        low_participation=processed.stats.get("low_participation", False),
    )

    return ReportContext(
        session_id=processed.session_id,
        date=_dt.now(tz=_tz.utc).strftime("%Y-%m-%d"),
        stats=stats,
        emoji_bar=_emoji_bar(processed.sentiment_counts, config.MAX_EMOJI_BAR),
        sentiment_counts=processed.sentiment_counts,
        themes=themes,
        bullets_well=bullets_well,
        bullets_improve=bullets_improve,
        all_items=anonymized_items,
        version=os.getenv("REPORT_VERSION", "0.1"),
    )
