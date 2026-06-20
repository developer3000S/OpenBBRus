"""MCP server backing the SEC Filing Viewer widget."""

from fastmcp import FastMCP

filing_viewer_mcp = FastMCP("SEC Filing Viewer")


def build_mcp_app():
    """Build the MCP ASGI app with CORS + Private Network Access headers."""
    from starlette.datastructures import Headers, MutableHeaders
    from starlette.middleware import Middleware

    expose = "mcp-session-id, mcp-protocol-version"

    class _Cors:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            headers = Headers(scope=scope)
            origin = headers.get("origin", "*")
            if (
                scope["method"] == "OPTIONS"
                and "access-control-request-method" in headers
            ):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"access-control-allow-origin", origin.encode()),
                            (b"access-control-allow-methods", b"*"),
                            (b"access-control-allow-headers", b"*"),
                            (b"access-control-allow-private-network", b"true"),
                            (b"access-control-max-age", b"600"),
                            (b"content-length", b"0"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b""})
                return

            async def _send(message):
                if message["type"] == "http.response.start":
                    out = MutableHeaders(scope=message)
                    out["access-control-allow-origin"] = origin
                    out["access-control-allow-private-network"] = "true"
                    out["access-control-expose-headers"] = expose
                await send(message)

            await self.app(scope, receive, _send)

    return filing_viewer_mcp.http_app(path="/mcp", middleware=[Middleware(_Cors)])


def document_to_markdown(url: str) -> str:
    """Return a SEC EDGAR filing document as agent-readable text/markdown."""
    import re

    from openbb_sec.utils.cache import cached_bytes
    from openbb_sec.utils.definitions import SEC_HEADERS
    from openbb_sec.utils.html2markdown import html_to_markdown

    if not url or not url.startswith(("https://www.sec.gov/", "https://efts.sec.gov/")):
        return "Only SEC EDGAR document URLs are supported."
    try:
        raw = cached_bytes(url, use_cache=True, headers=SEC_HEADERS) or b""
    except Exception as e:  # noqa: BLE001
        return f"Could not load the document: {e}"

    path = url.split("?", 1)[0].lower()
    if path.endswith(".pdf") or raw[:5] == b"%PDF-":
        return f"This document is a PDF and is not convertible to text here: {url}"

    text = raw.decode("utf-8", errors="ignore")
    if path.endswith((".htm", ".html")) or re.search(
        r"(?i)<html|<body|<!doctype", text[:2000]
    ):
        return html_to_markdown(text, base_url=url.rsplit("/", 1)[0] + "/")
    return text


_CURRENT: dict = {"url": None}


@filing_viewer_mcp.custom_route("/viewer-state", methods=["POST"])
async def _set_viewer_state(request):
    """Record the URL of the document currently shown in the Filing Viewer."""
    import contextlib

    from starlette.responses import JSONResponse

    body: dict = {}
    with contextlib.suppress(Exception):
        body = await request.json()
    _CURRENT["url"] = (body or {}).get("url") or None
    return JSONResponse({"ok": True})


@filing_viewer_mcp.tool
def get_filing_document(url: str | None = None) -> str:
    """Return the SEC filing document currently shown in the Filing Viewer."""
    target = url or _CURRENT["url"]
    if not target:
        return "No document is currently open in the Filing Viewer."
    return document_to_markdown(target)
