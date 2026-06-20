"""Unit tests for ``openbb_sec.utils.statement_widget``."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openbb_sec.utils.statement_widget import get_statement_widget_rows


def _records():
    return [
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "fiscal_year": 2024,
            "tag": "total_assets",
            "value": 100.0,
            "label": "Total Assets",
            "description": "All assets.",
            "source": "10-K filed 2025-02",
        },
        {
            "period_ending": "2023-12-31",
            "fiscal_period": "FY",
            "fiscal_year": 2023,
            "tag": "total_assets",
            "value": 90.0,
            "label": "Total Assets",
            "description": "All assets.",
            "source": "10-K filed 2024-02",
        },
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "fiscal_year": 2024,
            "tag": "total_liabilities",
            "value": 40.0,
            "label": "Total Liabilities",
            "description": "",
            "source": "",
        },
    ]


def _run(records=None, **kwargs):
    fake = SimpleNamespace(
        balance_sheet=_records() if records is None else records,
        income_statement=[],
        cash_flow=[],
    )
    kwargs.setdefault("symbol", "AAPL")
    kwargs.setdefault("statement_type", "balance")
    with patch(
        "openbb_sec.utils.company_facts.get_standardized_financials",
        AsyncMock(return_value=fake),
    ):
        return asyncio.run(get_statement_widget_rows(**kwargs))


def test_transposed_with_provenance():
    rows = _run(period="FY", transform="None", transpose=True, limit=10)
    assert {r["Line Item"] for r in rows} == {"Total Assets", "Total Liabilities"}
    assets = next(r for r in rows if r["Line Item"] == "Total Assets")
    assert assets["FY 2024-12-31"] == 100.0
    assert assets["FY 2023-12-31"] == 90.0
    assert "10-K filed 2025-02" in assets["provenance"]


def test_no_source_provenance_fallback():
    rows = _run(transpose=True)
    liabilities = next(r for r in rows if r["Line Item"] == "Total Liabilities")
    assert "No source detail" in liabilities["provenance"]


def test_provenance_collapses_when_source_uniform():
    records = [
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "tag": "total_assets",
            "value": 1,
            "label": "Total Assets",
            "source": "us-gaap:Assets",
        },
        {
            "period_ending": "2023-12-31",
            "fiscal_period": "FY",
            "tag": "total_assets",
            "value": 2,
            "label": "Total Assets",
            "source": "us-gaap:Assets",
        },
    ]
    prov = _run(records=records, transpose=True)[0]["provenance"]
    assert prov == "us-gaap:Assets"
    assert "FY" not in prov


def test_untransposed():
    rows = _run(transpose=False, limit=10)
    assert rows[0]["Period"].startswith("FY")
    assert "Total Assets" in rows[0]


def test_limit_restricts_periods():
    rows = _run(transpose=True, limit=1)
    period_cols = [
        k for k in rows[0] if k not in ("Line Item", "description", "provenance")
    ]
    assert len(period_cols) == 1


def test_empty_records():
    assert _run(records=[]) == []


def test_unknown_statement_type():
    with pytest.raises(ValueError, match="Unknown statement_type"):
        _run(statement_type="bogus")


def test_ttm_pop_invokes_pct_change():
    with patch(
        "openbb_sec.utils.company_facts._compute_pct_change",
        lambda records, mode: records,
    ):
        rows = _run(period="TTM", transform="% PoP")
    assert rows


def test_invalid_combo_falls_back_to_base_period():
    rows = _run(period="FY", transform="% PoP")
    assert {r["Line Item"] for r in rows} == {"Total Assets", "Total Liabilities"}


def test_drops_line_items_empty_across_all_periods():
    records = [
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "tag": "total_assets",
            "value": 100,
            "label": "Total Assets",
        },
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "tag": "restricted_cash",
            "value": None,
            "label": "Restricted Cash",
        },
        {
            "period_ending": "2023-12-31",
            "fiscal_period": "FY",
            "tag": "restricted_cash",
            "value": None,
            "label": "Restricted Cash",
        },
    ]
    items = {r["Line Item"] for r in _run(records=records, transpose=True)}
    assert "Total Assets" in items
    assert "Restricted Cash" not in items


def test_line_items_sorted_by_model_field_order():
    records = [
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "tag": "total_liabilities",
            "value": 1,
            "label": "Total Liabilities",
        },
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "tag": "cash_and_equivalents",
            "value": 2,
            "label": "Cash",
        },
        {
            "period_ending": "2024-12-31",
            "fiscal_period": "FY",
            "tag": "total_current_assets",
            "value": 3,
            "label": "Total Current Assets",
        },
    ]
    rows = _run(records=records, transpose=True)
    assert [r["Line Item"] for r in rows] == [
        "Cash",
        "Total Current Assets",
        "Total Liabilities",
    ]
