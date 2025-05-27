# app/logic/data_retrieval.py
from typing import Optional, List
import pandas as pd
import logging
import os # For __main__ example

from app.services.fred_service import FredService # Assuming fred_service.py is in app/services/
from app.models import FredSeriesInfo, FredDataPoint, FredSeriesData # Assuming models.py is in app/

logger = logging.getLogger(__name__)

class DataRetrievalService:
    def __init__(self, fred_service: FredService):
        if not fred_service:
            logger.error("DataRetrievalService initialized without a FredService instance.")
            raise ValueError("FredService instance is required.")
        self.fred_service = fred_service

    def get_series_data(self, series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[FredSeriesData]:
        logger.info(f"Attempting to retrieve series data for ID: {series_id} from {start_date} to {end_date}")

        raw_info = self.fred_service.get_series_info(series_id)
        if raw_info is None: # FredService.get_series_info returns a dict or None
            logger.warning(f"Could not retrieve series info for ID: {series_id}. Aborting data retrieval.")
            return None
        
        try:
            series_info = FredSeriesInfo(
                id=raw_info.get('id', series_id), 
                title=raw_info.get('title', 'N/A'),
                units=raw_info.get('units', 'N/A'),
                frequency=raw_info.get('frequency'),
                seasonal_adjustment=raw_info.get('seasonal_adjustment'), 
                seasonal_adjustment_short=raw_info.get('seasonal_adjustment_short'),
                notes=raw_info.get('notes'), 
                popularity=raw_info.get('popularity'),
                observation_start=raw_info.get('observation_start'),
                observation_end=raw_info.get('observation_end'),
                last_updated=raw_info.get('last_updated')
            )
        except Exception as e: 
            logger.error(f"Error mapping raw info to FredSeriesInfo for {series_id}: {e}", exc_info=True)
            return None

        series_pd_data = self.fred_service.get_series_data(series_id, start_date, end_date)
        if series_pd_data is None or series_pd_data.empty: 
            logger.warning(f"No data points found for series ID: {series_id} in the given date range.")
            return FredSeriesData(series_id=series_id, info=series_info, data=[])

        data_points: List[FredDataPoint] = []
        for date_idx, value in series_pd_data.items(): # series_pd_data is a pd.Series
            try:
                date_str = date_idx.strftime('%Y-%m-%d') if isinstance(date_idx, pd.Timestamp) else str(date_idx)
                value_float = float(value) if pd.notna(value) else None 
                if value_float is not None:
                    data_points.append(FredDataPoint(date=date_str, value=value_float))
                else:
                    logger.debug(f"Skipping NaN value for series {series_id} on date {date_str}")
            except Exception as e:
                logger.error(f"Error processing data point for {series_id} (Date: {date_idx}, Value: {value}): {e}", exc_info=True)
        
        return FredSeriesData(series_id=series_id, info=series_info, data=data_points)

    def search_series(self, search_text: str, limit: int = 10) -> List[FredSeriesInfo]:
        logger.info(f"Searching for series with text: '{search_text}', limit: {limit}")
        results_df = self.fred_service.search_series(search_text, limit=limit) 

        if results_df is None or results_df.empty:
            logger.info(f"No search results found for '{search_text}'.")
            return []

        series_info_list: List[FredSeriesInfo] = []
        for _, row in results_df.iterrows(): # results_df is a pd.DataFrame
            try:
                # Note: fredapi search results might have 'seasonal_adjustment_short'
                # and info might have 'seasonal_adjustment'. FredSeriesInfo has both.
                info = FredSeriesInfo(
                    id=row.get('id'),
                    title=row.get('title'),
                    units=row.get('units'),
                    frequency=row.get('frequency'),
                    seasonal_adjustment=row.get('seasonal_adjustment'), # Fallback if 'seasonal_adjustment_short' is not primary
                    seasonal_adjustment_short=row.get('seasonal_adjustment_short'),
                    notes=row.get('notes'), 
                    popularity=row.get('popularity'),
                    observation_start=row.get('observation_start'),
                    observation_end=row.get('observation_end'),
                    last_updated=row.get('last_updated') # Search results might also have this
                )
                series_info_list.append(info)
            except Exception as e: 
                logger.error(f"Error mapping search result row to FredSeriesInfo for id {row.get('id', 'UNKNOWN')}: {e}", exc_info=True)
        
        return series_info_list

if __name__ == '__main__':
    if os.getenv("FRED_API_KEY"):
        try:
            fred_service_instance = FredService()
            data_retrieval_service = DataRetrievalService(fred_service_instance)

            print("\n--- Test Search Series ---")
            search_results = data_retrieval_service.search_series("Real GDP", limit=3)
            if search_results:
                for item in search_results:
                    print(f"ID: {item.id}, Title: {item.title}, Popularity: {item.popularity}, SAS: {item.seasonal_adjustment_short}")
                
                if search_results[0]:
                    first_series_id = search_results[0].id
                    print(f"\n--- Test Get Series Data for {first_series_id} ---")
                    series_data = data_retrieval_service.get_series_data(first_series_id, start_date="2022-01-01", end_date="2023-01-01")
                    if series_data:
                        print(f"Series ID: {series_data.series_id}")
                        print(f"Title: {series_data.info.title}")
                        print(f"Units: {series_data.info.units}")
                        print(f"SA: {series_data.info.seasonal_adjustment}, SAS: {series_data.info.seasonal_adjustment_short}")
                        print(f"Number of data points: {len(series_data.data)}")
                        if series_data.data:
                            print("First 5 data points:")
                            for dp in series_data.data[:5]:
                                print(f"  Date: {dp.date}, Value: {dp.value}")
                    else:
                        print(f"Could not retrieve data for series {first_series_id}.")
            else:
                print("No series found in search.")
            
            print("\n--- Test Non-existent Series ---")
            non_existent_data = data_retrieval_service.get_series_data("NONEXISTENTSERIES")
            if non_existent_data is None:
                print("Correctly handled non-existent series: returned None.")
            elif not non_existent_data.data: # Case where info might exist (unlikely for truly non-existent) but no data
                 print(f"Correctly handled non-existent series: Info: {non_existent_data.info.title if non_existent_data.info else 'N/A'}, No data points.")
            else:
                print(f"Unexpectedly got data for non-existent series: {non_existent_data}")

        except ValueError as ve:
            print(f"ValueError during setup: {ve}")
        except Exception as e:
            print(f"An unexpected error occurred during __main__ testing: {e}", exc_info=True)
    else:
        print("FRED_API_KEY not set. Skipping DataRetrievalService example usage.")
