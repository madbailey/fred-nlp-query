# app/logic/data_processing.py
from typing import List, Optional, Dict, Any
import logging
import math # For CAGR calculation
from datetime import datetime

from app.models import FredSeriesData, FredDataPoint, ProcessedDataset, QueryDetails, FredSeriesInfo

logger = logging.getLogger(__name__)

class DataProcessingService:
    def __init__(self):
        pass

    def _find_first_valid_point(self, data_points: List[FredDataPoint]) -> Optional[FredDataPoint]:
        if not data_points:
            return None
        for point in data_points:
            # Assuming FredDataPoint.value can be 0, which is valid.
            if point.value is not None: 
                return point
        return None

    def _find_last_valid_point(self, data_points: List[FredDataPoint]) -> Optional[FredDataPoint]:
        if not data_points:
            return None
        for point in reversed(data_points):
            if point.value is not None:
                return point
        return None

    def normalize_series(self, series_data: FredSeriesData, base_value: float = 100.0) -> ProcessedDataset:
        logger.info(f"Normalizing series: {series_data.series_id}")
        
        if not series_data.data:
            logger.warning(f"Cannot normalize empty series: {series_data.series_id}")
            return ProcessedDataset(
                id=f"{series_data.series_id}_normalized_empty",
                name=f"{series_data.info.title} (Normalized - Empty)",
                data_points=[],
                metadata={"original_series_id": series_data.series_id, "normalization_base": base_value, "status": "empty_series"}
            )

        first_valid_point = self._find_first_valid_point(series_data.data)

        if first_valid_point is None or first_valid_point.value == 0: 
            logger.warning(f"Cannot normalize series {series_data.series_id}: No valid first point or first point value is 0.")
            return ProcessedDataset(
                id=f"{series_data.series_id}_normalization_failed",
                name=f"{series_data.info.title} (Normalization Failed)",
                data_points=list(series_data.data), # Return original data points (copy)
                metadata={
                    "original_series_id": series_data.series_id, 
                    "normalization_base": base_value,
                    "status": "normalization_failed",
                    "reason": "No valid first point or first point value is zero"
                }
            )
            
        base = first_valid_point.value
        normalized_data_points: List[FredDataPoint] = []
        for point in series_data.data:
            if point.value is not None:
                normalized_value = (point.value / base) * base_value
                normalized_data_points.append(FredDataPoint(date=point.date, value=normalized_value))
            else: 
                normalized_data_points.append(FredDataPoint(date=point.date, value=None))


        return ProcessedDataset(
            id=f"{series_data.series_id}_normalized",
            name=f"{series_data.info.title} (Normalized to {base_value} at {first_valid_point.date})",
            data_points=normalized_data_points,
            metadata={
                "original_series_id": series_data.series_id,
                "original_units": series_data.info.units,
                "normalized_units": f"Index (Base {base_value} = {first_valid_point.date})",
                "normalization_base_value_original": base,
                "normalization_base_date": first_valid_point.date,
                "status": "success"
            }
        )

    def calculate_total_growth_metric(self, series_data: FredSeriesData) -> Optional[Dict[str, Any]]:
        logger.info(f"Calculating total growth for series: {series_data.series_id}")
        if not series_data.data:
            logger.warning(f"Cannot calculate total growth for empty series: {series_data.series_id}")
            return None

        first_valid = self._find_first_valid_point(series_data.data)
        last_valid = self._find_last_valid_point(series_data.data)

        if not first_valid or not last_valid or first_valid.value is None or last_valid.value is None or first_valid.date == last_valid.date :
            logger.warning(f"Not enough valid or distinct data points to calculate total growth for {series_data.series_id}")
            return None
        
        if first_valid.value == 0:
            logger.warning(f"Cannot calculate total growth for {series_data.series_id}: starting value is 0.")
            # Determine growth based on end value
            growth_val = float('inf') if last_valid.value > 0 else (float('-inf') if last_valid.value < 0 else 0.0)
            return {"total_growth_percent": growth_val, 
                    "start_date": first_valid.date, "end_date": last_valid.date,
                    "start_value": first_valid.value, "end_value": last_valid.value, "notes": "Start value is 0"}


        total_growth = ((last_valid.value / first_valid.value) - 1) * 100

        return {
            "total_growth_percent": total_growth,
            "start_date": first_valid.date,
            "end_date": last_valid.date,
            "start_value": first_valid.value,
            "end_value": last_valid.value
        }

    def calculate_compound_annual_growth_rate_metric(self, series_data: FredSeriesData) -> Optional[Dict[str, Any]]:
        logger.info(f"Calculating CAGR for series: {series_data.series_id}")
        
        # Use internal helpers to get points directly, rather than relying on total_growth_metric structure
        first_valid = self._find_first_valid_point(series_data.data)
        last_valid = self._find_last_valid_point(series_data.data)

        if not first_valid or not last_valid or first_valid.value is None or last_valid.value is None:
            logger.warning(f"Not enough valid data points for CAGR calculation on {series_data.series_id}.")
            return None
            
        start_value = first_valid.value
        end_value = last_valid.value
        start_date_str = first_valid.date
        end_date_str = last_valid.date

        if start_value == 0: # Handles both start_value == 0 and end_value == 0, and start_value == 0 and end_value != 0
             logger.warning(f"Cannot calculate CAGR for {series_data.series_id}: start value is 0.")
             cagr_val = float('inf') if end_value > 0 else (float('-inf') if end_value < 0 else 0.0) # if end_value is also 0, cagr is 0
             # Years calculation is still relevant.
             try:
                start_datetime_temp = datetime.strptime(start_date_str, "%Y-%m-%d")
                end_datetime_temp = datetime.strptime(end_date_str, "%Y-%m-%d")
                years_temp = (end_datetime_temp - start_datetime_temp).days / 365.25
             except ValueError:
                years_temp = 0 # Or handle error appropriately
             return {"cagr_percent": cagr_val, "years": round(years_temp,2) if years_temp > 0 else 0.0, "notes": "Start value is 0"}

        try:
            start_datetime = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_datetime = datetime.strptime(end_date_str, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Could not parse dates for CAGR calculation: {start_date_str}, {end_date_str}", exc_info=True)
            return None

        years = (end_datetime - start_datetime).days / 365.25
        if years <= 0: 
            logger.warning(f"Cannot calculate CAGR for {series_data.series_id}: duration is zero or negative ({years:.2f} years).")
            if start_value == end_value: 
                 return {"cagr_percent": 0.0, "years": round(years,2), "notes": "Zero/negative duration, same start and end value"}
            else: 
                 cagr_val_zero_duration = float('inf') if end_value > start_value else float('-inf')
                 return {"cagr_percent": cagr_val_zero_duration, "years": round(years,2), "notes": "Zero/negative duration, different start/end values"}

        if (end_value < 0 and start_value > 0) or (end_value > 0 and start_value < 0) : # Base of exponentiation would be negative
            if (1 / years) % 1 != 0: # if years is not an integer, (negative_base ** fractional_power) is complex
                logger.warning(f"Cannot calculate CAGR for {series_data.series_id} due to negative ratio (e.g. {end_value}/{start_value}) and non-integer years leading to complex result.")
                return None
        
        # Handle case where start_value is negative. If end_value also negative, (neg/neg) is positive.
        # If start_value is negative and end_value is positive (or vice-versa), checked above.
        ratio = end_value / start_value
        if ratio < 0: # Should be caught by the previous block if power is fractional
             logger.warning(f"CAGR calculation resulted in negative base for exponentiation ({ratio}) which is problematic for non-integer years.")
             return None


        cagr = (math.pow(ratio, (1 / years)) - 1) * 100
        
        return {
            "cagr_percent": cagr,
            "years": round(years, 2)
        }

if __name__ == '__main__':
    processing_service = DataProcessingService()

    # Correctly instantiate FredSeriesInfo Pydantic model
    mock_series_info_model = FredSeriesInfo(id="GDP", title="Gross Domestic Product", units="Billions of Dollars", frequency="Quarterly", seasonal_adjustment="Seasonally Adjusted")
    
    print("\n--- Test Normalization ---")
    raw_data_norm = FredSeriesData(
        series_id="GDPNORM", 
        info=mock_series_info_model, 
        data=[
            FredDataPoint(date="2022-01-01", value=100.0),
            FredDataPoint(date="2022-04-01", value=102.0),
            FredDataPoint(date="2022-07-01", value=101.0),
            FredDataPoint(date="2022-10-01", value=105.0),
        ]
    )
    normalized_gdp = processing_service.normalize_series(raw_data_norm)
    if normalized_gdp and normalized_gdp.metadata.get("status") == "success":
        print(f"Normalized Series ID: {normalized_gdp.id}, Name: {normalized_gdp.name}")
        for dp in normalized_gdp.data_points:
            print(f"  Date: {dp.date}, Normalized Value: {dp.value:.2f}")
        print(f"Metadata: {normalized_gdp.metadata}")
    else:
        print("Normalization failed or returned unexpected result.")
        if normalized_gdp: print(f"Metadata: {normalized_gdp.metadata}")

    print("\n--- Test Normalization with leading None ---")
    raw_data_norm_leading_none = FredSeriesData(
        series_id="GDPLN", 
        info=mock_series_info_model, 
        data=[
            FredDataPoint(date="2022-01-01", value=None),
            FredDataPoint(date="2022-04-01", value=102.0), # This will be the base for normalization
            FredDataPoint(date="2022-07-01", value=101.0),
        ]
    )
    normalized_gdp_ln = processing_service.normalize_series(raw_data_norm_leading_none)
    if normalized_gdp_ln and normalized_gdp_ln.metadata.get("status") == "success":
        print(f"Normalized Series (leading None) ID: {normalized_gdp_ln.id}, Name: {normalized_gdp_ln.name}")
        for dp in normalized_gdp_ln.data_points: # First dp.value will be None
            print(f"  Date: {dp.date}, Normalized Value: {dp.value if dp.value is None else dp.value:.2f}")
        print(f"Metadata: {normalized_gdp_ln.metadata}") # Expected: base is 102.0 from 2022-04-01
    else:
        print("Normalization with leading None failed or returned unexpected result.")
        if normalized_gdp_ln: print(f"Metadata: {normalized_gdp_ln.metadata}")


    print("\n--- Test Total Growth ---")
    raw_data_growth = FredSeriesData(
        series_id="GDPGROWTH", 
        info=mock_series_info_model, 
        data=[
            FredDataPoint(date="2020-01-01", value=100.0),
            FredDataPoint(date="2021-01-01", value=110.0) # 10% growth
        ]
    )
    growth_stats = processing_service.calculate_total_growth_metric(raw_data_growth)
    if growth_stats:
        print(f"Total Growth: {growth_stats['total_growth_percent']:.2f}%")
        print(f"Details: {growth_stats}")
    else:
        print("Total growth calculation failed or returned None.")

    print("\n--- Test CAGR ---")
    cagr_stats = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_growth)
    if cagr_stats:
        print(f"CAGR: {cagr_stats['cagr_percent']:.2f}% over {cagr_stats['years']} years")
    else:
        print("CAGR calculation failed or returned None.")

    raw_data_cagr_multi_year = FredSeriesData(
        series_id="GDPCAGRMY", 
        info=mock_series_info_model, 
        data=[
            FredDataPoint(date="2020-01-01", value=100.0),
            FredDataPoint(date="2023-01-01", value=133.1) # (1.1)^3 = 1.331 => 10% CAGR over 3 years
        ]
    )
    cagr_stats_my = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_cagr_multi_year)
    if cagr_stats_my:
        print(f"CAGR (multi-year): {cagr_stats_my['cagr_percent']:.2f}% over {cagr_stats_my['years']} years")
    else:
        print("CAGR multi-year calculation failed or returned None.")

    print("\n--- Test Normalization with zero first value ---")
    raw_data_norm_zero = FredSeriesData(
        series_id="GDPZERO", 
        info=mock_series_info_model, 
        data=[FredDataPoint(date="2022-01-01", value=0.0), FredDataPoint(date="2022-04-01", value=10.0)]
    )
    normalized_zero = processing_service.normalize_series(raw_data_norm_zero)
    print(f"Normalization with zero first value status: {normalized_zero.metadata.get('status')}")
    print(f"Data points: {normalized_zero.data_points}")


    print("\n--- Test Growth with zero start value ---")
    growth_zero_start = processing_service.calculate_total_growth_metric(raw_data_norm_zero)
    print(f"Growth with zero start value: {growth_zero_start}")

    print("\n--- Test CAGR with zero start value ---")
    cagr_zero_start = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_norm_zero)
    print(f"CAGR with zero start value: {cagr_zero_start}")

    print("\n--- Test CAGR with same start/end date ---")
    raw_data_cagr_same_date = FredSeriesData(
        series_id="GDPSAMEDATE", 
        info=mock_series_info_model, 
        data=[FredDataPoint(date="2020-01-01", value=100.0), FredDataPoint(date="2020-01-01", value=100.0)]
    )
    cagr_same_date = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_cagr_same_date)
    print(f"CAGR with same start/end date: {cagr_same_date}")

    print("\n--- Test Total Growth with same start/end date ---")
    total_growth_same_date = processing_service.calculate_total_growth_metric(raw_data_cagr_same_date)
    print(f"Total growth with same start/end date: {total_growth_same_date}") # Expected: None

    print("\n--- Test CAGR with negative values leading to complex result ---")
    raw_data_cagr_neg_complex = FredSeriesData(
        series_id="GDPNEGCOMPLEX",
        info=mock_series_info_model,
        data=[
            FredDataPoint(date="2020-01-01", value=-100.0),
            FredDataPoint(date="2021-06-01", value=50.0) # 1.5 years, neg base, fractional power
        ]
    )
    cagr_neg_complex = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_cagr_neg_complex)
    print(f"CAGR with negative values (complex case): {cagr_neg_complex}") # Expected: None

    print("\n--- Test CAGR with negative values (integer years) ---")
    raw_data_cagr_neg_int_years = FredSeriesData(
        series_id="GDPNEGINT",
        info=mock_series_info_model,
        data=[
            FredDataPoint(date="2020-01-01", value=-100.0),
            FredDataPoint(date="2022-01-01", value=-121.0) # -121/-100 = 1.21. sqrt(1.21) = 1.1 => 10% CAGR. 2 years
        ]
    )
    # math.pow can handle negative base if exponent is integer, but (1/years) might not be perfect int
    # For CAGR, we generally assume values are positive. If values are negative, their magnitudes are often what's of interest.
    # The current CAGR logic might give (-1.21) ** (1/2) which is complex, or if math.pow handles it, it's (-100 * (1+r)^2 = -121)
    # This means (1+r)^2 = 1.21 => 1+r = 1.1 => r = 0.1 or 10%
    cagr_neg_int_years = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_cagr_neg_int_years)
    print(f"CAGR with negative values (integer years, valid ratio): {cagr_neg_int_years}") # Expected: 10%
    
    raw_data_cagr_neg_int_years_flip = FredSeriesData(
        series_id="GDPNEGINTFLIP",
        info=mock_series_info_model,
        data=[
            FredDataPoint(date="2020-01-01", value=-100.0),
            FredDataPoint(date="2022-01-01", value=121.0) # 121/-100 = -1.21. (2 years)
        ]
    )
    cagr_neg_int_years_flip = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_cagr_neg_int_years_flip)
    print(f"CAGR with negative values (integer years, sign flip): {cagr_neg_int_years_flip}") # Expected: None or error message

    print("\n--- Test Normalization with all None data ---")
    raw_data_norm_all_none = FredSeriesData(
        series_id="GDPALLNONE", 
        info=mock_series_info_model, 
        data=[
            FredDataPoint(date="2022-01-01", value=None),
            FredDataPoint(date="2022-04-01", value=None),
        ]
    )
    normalized_all_none = processing_service.normalize_series(raw_data_norm_all_none)
    print(f"Normalization with all None data status: {normalized_all_none.metadata.get('status')}")
    print(f"Data points: {normalized_all_none.data_points}") # Expected: normalization_failed
    
    print("\n--- Test Total Growth with all None data ---")
    growth_all_none = processing_service.calculate_total_growth_metric(raw_data_norm_all_none)
    print(f"Total Growth with all None data: {growth_all_none}") # Expected: None
    
    print("\n--- Test CAGR with all None data ---")
    cagr_all_none = processing_service.calculate_compound_annual_growth_rate_metric(raw_data_norm_all_none)
    print(f"CAGR with all None data: {cagr_all_none}") # Expected: None
