"""Tests for scraper parsing logic using mock HTML."""

import pytest

from localizer.db import Database, RFP
from localizer.scrapers.base import BaseScraper
from localizer.scrapers.multnomah import MultnomahScraper
from localizer.scrapers.portland import PortlandScraper


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class TestBaseScraper:
    def test_make_id_deterministic(self, db):
        class DummyScraper(BaseScraper):
            name = "test"
            base_url = ""
            def scrape(self):
                return []

        s = DummyScraper(db)
        id1 = s.make_id("abc", "123")
        id2 = s.make_id("abc", "123")
        id3 = s.make_id("abc", "456")
        assert id1 == id2
        assert id1 != id3
        assert len(id1) == 16

    def test_parse_date_formats(self, db):
        class DummyScraper(BaseScraper):
            name = "test"
            base_url = ""
            def scrape(self):
                return []

        s = DummyScraper(db)
        assert s.parse_date("01/15/2026") == "2026-01-15"
        assert s.parse_date("2026-01-15") == "2026-01-15"
        assert s.parse_date("January 15, 2026") == "2026-01-15"
        assert s.parse_date("Jan 15, 2026") == "2026-01-15"
        assert s.parse_date("01/15/2026 2:30 PM") == "2026-01-15"
        assert s.parse_date(None) is None
        assert s.parse_date("") is None

    def test_detect_type(self, db):
        class DummyScraper(BaseScraper):
            name = "test"
            base_url = ""
            def scrape(self):
                return []

        s = DummyScraper(db)
        assert s.detect_type("RFP for Website Redesign") == "RFP"
        assert s.detect_type("RFI - Market Research for Transit") == "RFI"
        assert s.detect_type("RFQ: Structural Engineering Services") == "RFQ"
        assert s.detect_type("IFB 2026-001 Road Paving") == "IFB"
        assert s.detect_type("ITB for Office Supplies") == "ITB"
        assert s.detect_type("SOQ for Architectural Services") == "SOQ"
        assert s.detect_type("Request for Proposal - IT Audit") == "RFP"
        assert s.detect_type("Request for Information: Cloud Services") == "RFI"
        assert s.detect_type("Request for Qualifications - Engineering") == "RFQ"
        assert s.detect_type("Personal Services Contract") == "PSS"
        assert s.detect_type("Professional Services: PM Support") == "PSS"
        assert s.detect_type("General maintenance work") == "other"
        assert s.detect_type("") == "other"
        assert s.detect_type(None) == "other"


class TestPortlandScraper:
    def test_parse_table(self, db):
        scraper = PortlandScraper(db)
        html = """
        <html><body>
        <table>
            <tr><th>Bid Number</th><th>Title</th><th>Due Date</th></tr>
            <tr>
                <td>BID-2026-001</td>
                <td><a href="/bids/001">Website Accessibility Audit</a></td>
                <td>04/15/2026</td>
            </tr>
            <tr>
                <td>BID-2026-002</td>
                <td><a href="/bids/002">Park Signage Replacement</a></td>
                <td>04/30/2026</td>
            </tr>
        </table>
        </body></html>
        """
        rfps = scraper._parse_portland_gov(scraper.soup(html), html)
        assert len(rfps) >= 2


class TestMultnomahScraper:
    def test_parse_jaggaer_table(self, db):
        scraper = MultnomahScraper(db)
        html = """
        <html><body>
        <table>
            <tr>
                <th>Event ID</th>
                <th>Event Name</th>
                <th>Close Date</th>
                <th>Category</th>
            </tr>
            <tr>
                <td>EVT-001</td>
                <td><a href="/events/001">IT Consulting Services</a></td>
                <td>05/01/2026</td>
                <td>Technology</td>
            </tr>
        </table>
        </body></html>
        """
        page = scraper.soup(html)
        # Simulate the scrape parsing
        rfps = []
        for table in page.find_all("table"):
            rows = table.find_all("tr")
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
            for row in rows[1:]:
                cells = row.find_all("td")
                data = {headers[i] if i < len(headers) else f"col{i}": cell for i, cell in enumerate(cells)}
                rfp = scraper._parse_row(data)
                if rfp:
                    rfps.append(rfp)

        assert len(rfps) == 1
        assert rfps[0].title == "IT Consulting Services"
        assert rfps[0].due_date == "2026-05-01"
        assert rfps[0].category == "Technology"


class TestDigest:
    def test_digest_generation(self, db):
        from localizer.digest import generate_digest

        db.upsert_rfp(RFP(id="d1", source="portland", title="Test RFP 1"))
        db.upsert_rfp(RFP(id="d2", source="multnomah", title="Test RFP 2"))

        text, html, rfps = generate_digest(db, mark_notified=False)
        assert len(rfps) == 2
        assert "Test RFP 1" in text
        assert "Test RFP 2" in text
        assert "<html>" in html

    def test_digest_marks_notified(self, db):
        from localizer.digest import generate_digest

        db.upsert_rfp(RFP(id="d1", source="test", title="Test"))
        generate_digest(db, mark_notified=True)

        assert len(db.get_unnotified_rfps()) == 0

    def test_empty_digest(self, db):
        from localizer.digest import generate_digest

        text, html, rfps = generate_digest(db)
        assert text == ""
        assert html == ""
        assert rfps == []


class TestEmail:
    def test_get_email_config_defaults(self):
        from localizer.email import get_email_config

        config = get_email_config()
        assert config["smtp_host"] == "smtp.gmail.com"
        assert config["smtp_port"] == 587

    def test_send_fails_without_config(self):
        from localizer.email import send_digest_email

        result = send_digest_email("text", "<html>html</html>", config={
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_pass": "",
            "email_to": "",
            "email_from": "",
        })
        assert result is False

    def test_send_builds_correct_message(self):
        """Verify the MIME message is constructed correctly without actually sending."""
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from unittest.mock import patch, MagicMock
        from localizer.email import send_digest_email

        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_pass": "pass",
            "email_to": "recipient@example.com",
            "email_from": "sender@example.com",
        }

        mock_smtp = MagicMock()
        with patch("localizer.email.smtplib.SMTP", return_value=mock_smtp):
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            result = send_digest_email(
                "text body", "<html>html body</html>",
                subject="Test Subject", config=config,
            )

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "pass")
        mock_smtp.sendmail.assert_called_once()
        call_args = mock_smtp.sendmail.call_args
        assert call_args[0][0] == "sender@example.com"
        assert call_args[0][1] == ["recipient@example.com"]
