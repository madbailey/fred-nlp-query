from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from fredapi import Fred
import os
import pandas as pd
import matplotlib.pyplot as plt
import io
from datetime import datetime, timedelta
import streamlit as st

fred = Fred(api_key=os.getenv("FRED_API_KEY"))

class SeriesSearchInput(BaseModel):
    search_text: str = Field(description="Text to search for in FRED series")
    limit: int = Field(default=5, description="Number of results to return")

class SeriesDataInput(BaseModel):
    series_id: str = Field(description="FRED series ID")
    start_date: Optional[str] = Field(default=None, description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(default=None, description="End date in YYYY-MM-DD format")  

def search_fred_series(search_text: str, limit:int = 5):
    """search fred for relevant data series"""
    try:
        results = fred.search(search_text, limit=limit)
        if results.empty:
            return "No Series Found Matching Your Search."
        output = "Found the following series:\n\n"
        for _, row in results.iterrows():
            output += f"- ID: {row['id']}, Title: {row['title']}\n"

        return output
    except Exception as e:
        return f"Error search FRED: {str(e)}"

def get_fred_data(series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Get data for a specific FRED series with optional date range"""
    try:
        # Default to last 10 years if no dates provided
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d")
            
        # Get data
        data = fred.get_series(series_id, start_date, end_date)
        
        # Store in session state for visualization
        st.session_state[f"data_{series_id}"] = data
        
        # Return summary
        return f"Retrieved {len(data)} data points for series {series_id}. Use the visualize_data tool to view this data."
    except Exception as e:
        return f"Error fetching data: {str(e)}"

def visualize_data(series_id: str, title: Optional[str] = None):
    """Create a visualization of previously fetched FRED data"""
    try:
        if f"data_{series_id}" not in st.session_state:
            return f"No data found for series {series_id}. Fetch it first with get_fred_data."
            
        data = st.session_state[f"data_{series_id}"]
        series_info = fred.get_series_info(series_id)
        
        if not title:
            title = series_info['title'] if 'title' in series_info else f"Series {series_id}"
            
        # Create the chart in memory
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(data.index, data.values)
        ax.set_title(title)
        ax.set_xlabel('Date')
        ax.set_ylabel(series_info.get('units', 'Value'))
        ax.grid(True)
        
        # Store the figure in session state for Streamlit to display
        st.session_state['current_figure'] = fig
        
        return f"Created visualization for {series_id}. The chart is now available for display."
    except Exception as e:
        return f"Error creating visualization: {str(e)}"

# Create LangChain tool objects
fred_search_tool = StructuredTool.from_function(
    func=search_fred_series,
    name="search_fred_series",
    description="Search for economic data series in the FRED database",
    args_schema=SeriesSearchInput
)

fred_data_tool = StructuredTool.from_function(
    func=get_fred_data,
    name="get_fred_data",
    description="Get data for a specific FRED series with optional date range",
    args_schema=SeriesDataInput
)

visualize_tool = StructuredTool.from_function(
    func=visualize_data,
    name="visualize_data",
    description="Create a visualization of previously fetched FRED data"
)

# List of all tools
fred_tools = [fred_search_tool, fred_data_tool, visualize_tool]