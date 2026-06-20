"""Helpers for extracting governance tables from proxy statements (DEF 14A)."""

from collections.abc import Callable


def _attr(tag, name: str) -> str:
    """Return a tag attribute as a string, joining multi-valued attributes."""
    value = tag.get(name)
    if isinstance(value, list):
        return " ".join(value)
    return value or ""


async def resolve_proxy_url(
    symbol: str, calendar_year: "int | None", use_cache: bool
) -> "str | None":
    """Return the DEF 14A main-document URL, defaulting to the most recent."""
    from openbb_sec.models.company_filings import SecCompanyFilingsFetcher

    filings = await SecCompanyFilingsFetcher().fetch_data(
        {"symbol": symbol, "form_type": "DEF_14A", "use_cache": use_cache}, {}
    )
    rows = [
        (str(getattr(f, "filing_date", "")), getattr(f, "report_url", None))
        for f in filings
    ]
    rows = [(d, u) for d, u in rows if u]
    if not rows:
        return None
    if calendar_year is not None:
        match = [(d, u) for d, u in rows if d[:4] == str(calendar_year)]
        if match:
            return max(match)[1]
    return rows[0][1]


def _table_markdown(html: str, predicate: "Callable[[str], bool]") -> str:
    """Return the first table whose lowercased text matches ``predicate``."""
    import re

    from bs4 import BeautifulSoup

    from openbb_sec.utils.html2markdown import convert_table

    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        text = re.sub(r"\s+", " ", table.get_text(" ", strip=True)).lower()
        if predicate(text):
            return convert_table(table).strip()
    return ""


def summary_compensation_table(html: str) -> str:
    """Return the Summary Compensation Table (Reg S-K Item 402(c)) as markdown."""
    return _table_markdown(
        html,
        lambda t: (
            "salary" in t
            and "total" in t
            and "stock award" in t
            and "principal position" in t
            and "year" in t
        ),
    )


def beneficial_owners_table(html: str) -> str:
    """Return the security-ownership table that lists 5%+ beneficial owners."""
    return _table_markdown(
        html,
        lambda t: (
            (
                "percent of class" in t
                or "percent of common stock" in t
                or "percent of common shares" in t
                or "percent of outstanding" in t
            )
            and (
                "beneficial owner" in t
                or "name and address" in t
                or "beneficially owned" in t
            )
        ),
    )


def management_ownership_table(html: str) -> str:
    """Return the directors-and-executive-officers share-ownership table."""
    return _table_markdown(
        html, lambda t: "directors and executive officers as a group" in t
    )


_PVP_NUMERIC = {
    "PeoTotalCompAmt": "peo_total_compensation",
    "PeoActuallyPaidCompAmt": "peo_compensation_actually_paid",
    "NonPeoNeoAvgTotalCompAmt": "average_neo_total_compensation",
    "NonPeoNeoAvgCompActuallyPaidAmt": "average_neo_compensation_actually_paid",
    "TotalShareholderRtnAmt": "total_shareholder_return",
    "PeerGroupTotalShareholderRtnAmt": "peer_group_total_shareholder_return",
    "NetIncomeLoss": "net_income",
    "CoSelectedMeasureAmt": "company_selected_measure",
}


def _ix_number(tag) -> "float | None":
    """Parse an inline-XBRL numeric fact, applying sign and scale."""
    text = tag.get_text(strip=True).replace(",", "").replace("$", "").replace("%", "")
    text = text.replace("—", "").replace("\xa0", "").strip()
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    value *= 10 ** int(tag.get("scale") or 0)
    if (tag.get("sign") or "") == "-":
        value = -value
    return value


def pay_versus_performance(html: str) -> list[dict]:
    """Return the Pay Versus Performance table from inline XBRL facts, by year."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    ctx_year: dict[str, str] = {}
    for ctx in soup.find_all(lambda t: t.name and t.name.endswith("context")):
        if ctx.find(lambda t: t.name and "explicitmember" in t.name):
            continue
        period = ctx.find(lambda t: t.name and t.name.endswith("period"))
        if not period:
            continue
        date = period.find(lambda t: t.name and t.name.endswith(("enddate", "instant")))
        if date and date.get_text(strip=True)[:4].isdigit():
            ctx_year[_attr(ctx, "id")] = date.get_text(strip=True)[:4]

    rows: dict[str, dict] = {}
    for fact in soup.find_all(lambda t: t.name and t.name.endswith("nonfraction")):
        concept = _attr(fact, "name").split(":")[-1]
        field = _PVP_NUMERIC.get(concept)
        year = ctx_year.get(_attr(fact, "contextref"))
        if not field or not year:
            continue
        rows.setdefault(year, {"year": int(year)})[field] = _ix_number(fact)

    if not rows:
        return []

    measure = soup.find(
        lambda t: (
            t.name
            and t.name.endswith("nonnumeric")
            and (t.get("name") or "").split(":")[-1]
            in {"MeasureName", "CoSelectedMeasureName"}
        )
    )
    measure_name = measure.get_text(" ", strip=True) if measure else None
    if measure_name:
        for row in rows.values():
            row["company_selected_measure_name"] = measure_name

    return [rows[y] for y in sorted(rows, reverse=True)]
