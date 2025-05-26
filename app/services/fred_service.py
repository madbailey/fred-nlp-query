# app/services/fred_service.py
import os
import pandas as pd
from typing import Optional, Dict, Any
from fredapi import Fred
import streamlit as st # For caching
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a generic error handling decorator for service methods
def handle_fred_api_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e: # Catch a broad range of exceptions initially
            # Log the specific error for debugging
            logger.error(f"FRED API error in {func.__name__}: {e}", exc_info=True)
            # For now, return None. Could be enhanced to return specific error objects or raise custom exceptions.
            return None
    return wrapper

class FredService:
    def __init__(self):
        self.api_key = os.getenv("FRED_API_KEY")
        if not self.api_key:
            logger.error("FRED_API_KEY environment variable not set.")
            raise ValueError("FRED_API_KEY must be set.")
        self.client = Fred(api_key=self.api_key)

    @st.cache_data(ttl=3600) # Cache for 1 hour
    @handle_fred_api_errors
    def search_series(self, search_text: str, limit: int = 10) -> Optional[pd.DataFrame]:
        logger.info(f"Searching FRED series for: '{search_text}' with limit {limit}")
        results = self.client.search(search_text, limit=limit)
        if results is None or results.empty:
            logger.info(f"No series found for: '{search_text}'")
            return pd.DataFrame() # Return empty DataFrame for consistency
        return results

    @st.cache_data(ttl=3600) # Cache for 1 hour
    @handle_fred_api_errors
    def get_series_data(self, series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.Series]:
        logger.info(f"Fetching FRED data for series: {series_id}, start: {start_date}, end: {end_date}")
        data = self.client.get_series(series_id, observation_start=start_date, observation_end=end_date)
        if data is None or data.empty:
            logger.info(f"No data found for series: {series_id}")
            return pd.Series(dtype=float) # Return empty Series for consistency
        return data

    @st.cache_data(ttl=3600) # Cache for 1 hour
    @handle_fred_api_errors
    def get_series_info(self, series_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Fetching FRED series info for: {series_id}")
        info = self.client.get_series_info(series_id)
        if info is None or info.empty:
            logger.info(f"No info found for series: {series_id}")
            return None
        return info.to_dict() # Convert Pandas Series to Dict

# Example usage (optional, for testing within the file)
if __name__ == '__main__':
    # This part would require FRED_API_KEY to be set in the environment
    # For local testing, you might temporarily set it or use a .env file with python-dotenv
    if os.getenv("FRED_API_KEY"):
        service = FredService()
        
        # Test search
        search_results = service.search_series("GDP")
        if search_results is not None and not search_results.empty:
            print("Search Results:")
            print(search_results.head())
            # Ensure 'id' column exists before trying to access it
            if 'id' in search_results.columns and not search_results.empty:
                gdp_id = search_results.iloc[0]['id']
            
                # Test get_series_data
                gdp_data = service.get_series_data(gdp_id, start_date="2020-01-01", end_date="2023-01-01")
                if gdp_data is not None and not gdp_data.empty:
                    print("\nGDP Data:")
                    print(gdp_data.head())
                
                # Test get_series_info
                gdp_info = service.get_series_info(gdp_id)
                if gdp_info:
                    print("\nGDP Info:")
                    print(gdp_info)
            else:
                print("No 'id' column in search results or results are empty.")
        else:
            print("Search returned no results or an error occurred.")
    else:
        print("FRED_API_KEY not set. Skipping example usage.")
