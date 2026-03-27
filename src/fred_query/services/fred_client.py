from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from fred_query.errors import ConfigurationError, UpstreamServiceError
from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.resolved_series import SeriesMetadata, SeriesSearchMatch


class FREDAPIError(UpstreamServiceError):
    """Raised when a FRED request fails."""

    def __init__(self, message: str) -> None:
        super().__init__("fred", message)


class FREDClient:
    """Thin, explicit client for the FRED REST API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.stlouisfed.org/fred",
        timeout_seconds: float = 20.0,
        max_retries: int = 1,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ConfigurationError("A FRED API key is required.")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {"api_key": self.api_key, "file_type": "json", **params}
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.get(endpoint, params=query)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and payload.get("error_code"):
                    message = payload.get("error_message", "FRED returned an API error.")
                    raise FREDAPIError(message)
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break

        raise FREDAPIError(f"FRED request failed for {endpoint}: {last_error}") from last_error

    @staticmethod
    def _source_url(series_id: str) -> str:
        return f"https://fred.stlouisfed.org/series/{series_id}"

    def search_series(
        self,
        search_text: str,
        limit: int = 10,
        *,
        tag_names: str | None = None,
        filter_variable: str | None = None,
        filter_value: str | None = None,
    ) -> list[SeriesSearchMatch]:
        params: dict[str, Any] = {"search_text": search_text, "limit": limit}
        if tag_names:
            params["tag_names"] = tag_names
        if filter_variable and filter_value:
            params["filter_variable"] = filter_variable
            params["filter_value"] = filter_value

        payload = self._request("series/search", params=params)
        matches = []
        for item in payload.get("seriess", []):
            series_id = item["id"]
            matches.append(
                SeriesSearchMatch(
                    series_id=series_id,
                    title=item["title"],
                    units=item.get("units_short") or item.get("units"),
                    frequency=item.get("frequency_short") or item.get("frequency"),
                    seasonal_adjustment=item.get("seasonal_adjustment_short") or item.get("seasonal_adjustment"),
                    notes=item.get("notes"),
                    popularity=item.get("popularity"),
                    source_url=self._source_url(series_id),
                )
            )

        return matches

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        payload = self._request("series", params={"series_id": series_id})
        items = payload.get("seriess", [])
        if not items:
            raise FREDAPIError(f"No metadata found for series {series_id}.")

        item = items[0]
        return SeriesMetadata(
            series_id=series_id,
            title=item["title"],
            units=item.get("units_short") or item.get("units") or "Unknown",
            frequency=item.get("frequency_short") or item.get("frequency") or "Unknown",
            seasonal_adjustment=item.get("seasonal_adjustment_short") or item.get("seasonal_adjustment"),
            notes=item.get("notes"),
            source_url=self._source_url(series_id),
        )

    def get_series_observations(
        self,
        series_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        frequency: str | None = None,
        aggregation_method: str | None = None,
        limit: int | None = None,
        sort_order: str | None = None,
    ) -> list[ObservationPoint]:
        params: dict[str, Any] = {"series_id": series_id}
        if start_date is not None:
            params["observation_start"] = start_date.isoformat()
        if end_date is not None:
            params["observation_end"] = end_date.isoformat()
        if frequency:
            params["frequency"] = frequency
        if aggregation_method:
            params["aggregation_method"] = aggregation_method
        if limit is not None:
            params["limit"] = limit
        if sort_order:
            params["sort_order"] = sort_order

        payload = self._request("series/observations", params=params)
        observations: list[ObservationPoint] = []
        for item in payload.get("observations", []):
            raw_value = item.get("value", ".")
            if raw_value == ".":
                continue

            observations.append(
                ObservationPoint(
                    date=date.fromisoformat(item["date"]),
                    value=float(raw_value),
                )
            )

        return observations

    def get_series_vintage_dates(self, series_id: str, limit: int = 1000) -> list[date]:
        """
        Get the dates in history when a series' data values were revised or new data released.

        Args:
            series_id: The ID of the series to retrieve vintage dates for
            limit: Maximum number of vintage dates to return

        Returns:
            List of dates when the series was updated with new data
        """
        payload = self._request(
            "series/vintagedates",
            params={"series_id": series_id, "limit": limit},
        )
        return [date.fromisoformat(value) for value in payload.get("vintage_dates", [])]

    def get_series_observations_for_vintage_date(
        self,
        series_id: str,
        vintage_date: date,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        frequency: str | None = None,
        aggregation_method: str | None = None,
        limit: int | None = None,
        sort_order: str | None = None,
    ) -> list[ObservationPoint]:
        """
        Get series observations as they existed on a specific vintage date.
        This allows you to see what data was available on a specific date in history.

        Args:
            series_id: The ID of the series to retrieve
            vintage_date: The vintage date to get observations for
            start_date: Optional start date for observations
            end_date: Optional end date for observations
            frequency: Observation frequency (e.g., 'm' for monthly)
            aggregation_method: Aggregation method ('avg', 'sum', 'eop')
            limit: Maximum number of observations to return
            sort_order: Sort order ('asc', 'desc')

        Returns:
            List of observation points as they existed on the vintage date
        """
        params: dict[str, Any] = {
            "series_id": series_id,
            "vintage_dates": vintage_date.isoformat()  # Parameter name for vintage date
        }
        if start_date is not None:
            params["observation_start"] = start_date.isoformat()
        if end_date is not None:
            params["observation_end"] = end_date.isoformat()
        if frequency:
            params["frequency"] = frequency
        if aggregation_method:
            params["aggregation_method"] = aggregation_method
        if limit is not None:
            params["limit"] = limit
        if sort_order:
            params["sort_order"] = sort_order

        payload = self._request("series/observations", params=params)
        observations: list[ObservationPoint] = []
        for item in payload.get("observations", []):
            raw_value = item.get("value", ".")
            if raw_value == ".":
                continue

            observations.append(
                ObservationPoint(
                    date=date.fromisoformat(item["date"]),
                    value=float(raw_value),
                )
            )

        return observations
