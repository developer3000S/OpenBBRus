"""Tests for the SEC Filing Viewer MCP server."""

from unittest.mock import patch

from starlette.testclient import TestClient

from openbb_sec.utils import filing_viewer_mcp as mcp


def test_document_to_markdown_rejects_non_sec():
    """Non-SEC URLs are rejected."""
    out = mcp.document_to_markdown("https://example.com/x.htm")
    assert out.startswith("Only SEC")


def test_document_to_markdown_load_error():
    """A transport error is reported rather than raised."""
    with patch("openbb_sec.utils.cache.cached_bytes", side_effect=RuntimeError("boom")):
        out = mcp.document_to_markdown("https://www.sec.gov/a.htm")
    assert out.startswith("Could not load")


def test_document_to_markdown_pdf():
    """A PDF is described, not converted, by magic bytes or extension."""
    with patch("openbb_sec.utils.cache.cached_bytes", return_value=b"%PDF-1.7"):
        assert "PDF" in mcp.document_to_markdown("https://www.sec.gov/a.htm")
    with patch("openbb_sec.utils.cache.cached_bytes", return_value=b"x"):
        assert "PDF" in mcp.document_to_markdown("https://www.sec.gov/a.pdf")


def test_document_to_markdown_html():
    """HTML is converted to markdown."""
    with (
        patch(
            "openbb_sec.utils.cache.cached_bytes",
            return_value=b"<html><body>Hi</body></html>",
        ),
        patch("openbb_sec.utils.html2markdown.html_to_markdown", return_value="# Hi"),
    ):
        assert mcp.document_to_markdown("https://www.sec.gov/a.htm") == "# Hi"


def test_document_to_markdown_text():
    """Non-HTML text is returned as-is."""
    with patch(
        "openbb_sec.utils.cache.cached_bytes", return_value=b'<?xml version="1.0"?><x/>'
    ):
        out = mcp.document_to_markdown("https://www.sec.gov/a.xml")
    assert out.startswith("<?xml")


def test_get_filing_document_uses_url():
    """A supplied URL is converted directly."""
    with patch.object(mcp, "document_to_markdown", return_value="MD"):
        assert mcp.get_filing_document("https://www.sec.gov/a.htm") == "MD"


def test_get_filing_document_uses_current(monkeypatch):
    """With no URL, the document currently in the viewer is used."""
    monkeypatch.setitem(mcp._CURRENT, "url", "https://www.sec.gov/cur.htm")
    with patch.object(mcp, "document_to_markdown", return_value="CUR"):
        assert mcp.get_filing_document() == "CUR"


def test_get_filing_document_no_document(monkeypatch):
    """With no URL and nothing open, an informative message is returned."""
    monkeypatch.setitem(mcp._CURRENT, "url", None)
    assert "No document" in mcp.get_filing_document()


def test_build_mcp_app_preflight_and_viewer_state(monkeypatch):
    """The app answers the PNA preflight and records pushed viewer state."""
    monkeypatch.setitem(mcp._CURRENT, "url", None)
    with TestClient(mcp.build_mcp_app()) as client:
        preflight = client.options(
            "/mcp",
            headers={
                "Origin": "https://pro.openbb.dev",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers.get("access-control-allow-private-network") == "true"
        client.post("/viewer-state", json={"url": "https://www.sec.gov/x.htm"})
    assert mcp._CURRENT["url"] == "https://www.sec.gov/x.htm"
