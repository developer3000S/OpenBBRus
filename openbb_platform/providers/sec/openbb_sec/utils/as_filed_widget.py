"""Pivot as-filed SEC statements into period-ending columns for Workspace widgets."""

from types import SimpleNamespace


async def get_as_filed_widget_rows(
    symbol: str,
    statement_type: str,
    calendar_year: str | None = None,
    calendar_period: str | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Return an as-filed statement pivoted to period-ending columns, newest first."""
    from openbb_sec.models.sec_financials import (
        FinancialStatements,
        resolve_section_url,
    )

    query = SimpleNamespace(
        symbol=symbol,
        url=None,
        calendar_year=calendar_year,
        calendar_period=calendar_period,
        use_cache=use_cache,
    )
    url = await resolve_section_url(query, annual_default=False)
    if not url:
        return []

    statements = FinancialStatements.from_url(url, use_cache)
    data, _ = statements.get_statement(statement_type)
    if data is None or data.empty:
        return []

    records = data.to_dict("records")

    if "period_ending" not in data.columns:
        return [
            {"order": index + 1, **{k: v for k, v in record.items() if k != "tag"}}
            for index, record in enumerate(records)
        ]

    periods = sorted(
        {str(r["period_ending"]) for r in records if r.get("period_ending")},
        reverse=True,
    )
    rows: dict = {}
    order: list = []
    for record in records:
        key = (record.get("order"), record.get("label"), record.get("unit"))
        if key not in rows:
            row = {
                "order": record.get("order"),
                "label": record.get("label"),
                "unit": record.get("unit"),
            }
            row.update({period_ending: None for period_ending in periods})
            rows[key] = row
            order.append(key)
        period_ending = str(record.get("period_ending"))
        if period_ending in rows[key]:
            rows[key][period_ending] = record.get("value")

    return [rows[key] for key in order]
