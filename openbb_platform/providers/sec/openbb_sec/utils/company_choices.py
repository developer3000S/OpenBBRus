"""Company-choice options for SEC Workspace widgets, sourced from DoltHub."""

_DOLT_URL = "https://www.dolthub.com/api/v1alpha1/deeleeramone/sec-company-facts/main"

_PAGE_SIZE = 1000

_CACHE_KEY = "sec_company_choices"

_COMPANIES_SQL = """
SELECT pt.ticker AS ticker, c.entity_name AS name, pt.cik AS cik,
       min(t.`rank`) AS `rank`
FROM primary_tickers pt
JOIN companies c ON c.cik = pt.cik
JOIN tickers t ON t.cik = pt.cik AND t.ticker = pt.ticker
JOIN processed_ciks p ON p.cik = pt.cik
WHERE p.has_balance AND p.has_income AND p.has_cash_flow
GROUP BY pt.ticker, c.entity_name, pt.cik
ORDER BY `rank` ASC, ticker ASC
"""


async def get_company_choices(use_cache: bool = True) -> list[dict]:
    """Return symbol-dropdown choices for every company with standardized financials."""
    from urllib.parse import quote

    from openbb_sec.utils.cache import aget_cached, aset_cached, cached_request

    if use_cache:
        cached = await aget_cached(_CACHE_KEY)
        if cached is not None:
            return cached

    base = " ".join(_COMPANIES_SQL.split())
    rows: list = []
    offset = 0
    while True:
        url = f"{_DOLT_URL}?q={quote(f'{base} LIMIT {_PAGE_SIZE} OFFSET {offset}')}"
        response = await cached_request(
            url, use_cache=use_cache, expire=86400, timeout=180
        )
        page = response.get("rows", []) if isinstance(response, dict) else []
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    choices = [
        {
            "label": row.get("name") or row.get("ticker"),
            "value": row.get("ticker"),
            "extraInfo": {
                "description": f"{row.get('ticker')} | {row.get('cik')}",
                "rightOfDescription": row.get("sic_name") or "",
            },
        }
        for row in rows
        if row.get("ticker")
    ]

    if use_cache and choices:
        await aset_cached(_CACHE_KEY, choices, expire=86400)
    return choices
