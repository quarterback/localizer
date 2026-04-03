"""Tests for the database layer."""

import tempfile
from pathlib import Path

import pytest

from localizer.db import Database, RFP


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def test_upsert_new_rfp(db):
    rfp = RFP(id="test1", source="test", title="Test RFP")
    assert db.upsert_rfp(rfp) is True


def test_upsert_existing_rfp(db):
    rfp = RFP(id="test1", source="test", title="Test RFP")
    db.upsert_rfp(rfp)
    assert db.upsert_rfp(rfp) is False


def test_get_open_rfps(db):
    db.upsert_rfp(RFP(id="open1", source="portland", title="Open RFP", status="open"))
    db.upsert_rfp(RFP(id="closed1", source="portland", title="Closed RFP", status="closed"))

    open_rfps = db.get_open_rfps()
    assert len(open_rfps) == 1
    assert open_rfps[0]["id"] == "open1"


def test_get_open_rfps_by_source(db):
    db.upsert_rfp(RFP(id="p1", source="portland", title="Portland RFP"))
    db.upsert_rfp(RFP(id="m1", source="multnomah", title="Multnomah RFP"))

    portland = db.get_open_rfps(source="portland")
    assert len(portland) == 1
    assert portland[0]["source"] == "portland"


def test_search(db):
    db.upsert_rfp(RFP(id="s1", source="test", title="Website Redesign Project"))
    db.upsert_rfp(RFP(id="s2", source="test", title="Park Maintenance Contract"))
    db.upsert_rfp(RFP(
        id="s3", source="test", title="IT Support",
        description="Website hosting and maintenance",
    ))

    results = db.search("website")
    assert len(results) == 2
    titles = {r["title"] for r in results}
    assert "Website Redesign Project" in titles


def test_unnotified_flow(db):
    db.upsert_rfp(RFP(id="n1", source="test", title="New RFP"))
    db.upsert_rfp(RFP(id="n2", source="test", title="Another RFP"))

    unnotified = db.get_unnotified_rfps()
    assert len(unnotified) == 2

    db.mark_notified(["n1"])
    unnotified = db.get_unnotified_rfps()
    assert len(unnotified) == 1
    assert unnotified[0]["id"] == "n2"


def test_scrape_log(db):
    db.log_scrape("portland", "success", rfps_found=5, rfps_new=3)
    db.log_scrape("multnomah", "error", error="Connection timeout")

    history = db.get_scrape_history()
    assert len(history) == 2
    assert history[0]["source"] == "multnomah"  # most recent first
    assert history[0]["status"] == "error"


def test_update_preserves_first_seen(db):
    rfp = RFP(id="u1", source="test", title="Original Title")
    db.upsert_rfp(rfp)

    original = db.get_open_rfps()[0]
    first_seen = original["first_seen"]

    rfp.title = "Updated Title"
    db.upsert_rfp(rfp)

    updated = db.get_open_rfps()[0]
    assert updated["first_seen"] == first_seen
    assert updated["title"] == "Updated Title"
