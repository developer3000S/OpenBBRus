"""SEC Management Ownership Model."""

from typing import Any

from openbb_core.provider.abstract.data import Data
from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.abstract.query_params import QueryParams
from pydantic import Field, field_validator


class SecManagementOwnershipQueryParams(QueryParams):
    """SEC Management Ownership Query.

    The share ownership of directors and executive officers from the company's
    proxy statement (DEF 14A), Security Ownership of Management.
    """

    symbol: str = Field(description="Symbol to get data for.")
    calendar_year: int | None = Field(
        default=None,
        description="Calendar year the proxy was filed. Defaults to the most recent.",
    )
    use_cache: bool = Field(
        default=True,
        description="Use the cache for downloaded filings. Default is True.",
    )

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _to_upper(cls, v):
        """Upper-case the symbol."""
        return v.upper() if isinstance(v, str) else v

    @field_validator("calendar_year", mode="before", check_fields=False)
    @classmethod
    def _empty_to_none(cls, v):
        """Treat an empty string as None (most recent filing)."""
        return None if v == "" else v


class SecManagementOwnershipData(Data):
    """SEC Management Ownership Data."""

    content: str = Field(
        description="The directors and executive officers ownership table from the"
        " proxy (DEF 14A) as a formatted markdown table."
    )


class SecManagementOwnershipFetcher(
    Fetcher[SecManagementOwnershipQueryParams, SecManagementOwnershipData]
):
    """SEC Management Ownership Fetcher."""

    @staticmethod
    def transform_query(
        params: dict[str, Any],
    ) -> SecManagementOwnershipQueryParams:
        """Transform the query."""
        return SecManagementOwnershipQueryParams(**params)

    @staticmethod
    async def aextract_data(
        query: SecManagementOwnershipQueryParams,
        credentials: dict[str, str] | None,
        **kwargs: Any,
    ) -> dict:
        """Extract the directors/executive officers ownership table (DEF 14A)."""
        from openbb_core.provider.utils.errors import EmptyDataError

        from openbb_sec.models.sec_filing import Filing
        from openbb_sec.utils.proxy_statement import (
            management_ownership_table,
            resolve_proxy_url,
        )

        url = await resolve_proxy_url(
            query.symbol, query.calendar_year, query.use_cache
        )
        if not url and query.calendar_year is not None:
            url = await resolve_proxy_url(query.symbol, None, query.use_cache)
        if not url:
            raise EmptyDataError(
                f"No proxy statement (DEF 14A) was found for {query.symbol}."
            )

        html = await Filing._adownload_file(url, query.use_cache)
        content = management_ownership_table(html or "")
        if not content:
            raise EmptyDataError(
                "No management ownership table was found in the proxy statement for"
                f" {query.symbol}."
            )

        return {"content": content}

    @staticmethod
    def transform_data(
        query: SecManagementOwnershipQueryParams, data: dict, **kwargs: Any
    ) -> SecManagementOwnershipData:
        """Transform the data."""
        return SecManagementOwnershipData.model_validate(data)
