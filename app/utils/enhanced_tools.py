from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal, Union
from fredapi import Fred
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import io
from datetime import datetime, timedelta
import streamlit as st
import re

# Initialize FRED API
fred = Fred(api_key=os.getenv("FRED_API_KEY"))

# Query classification
def classify_query_type(query_text: str):
    """
    Determines if a query is for a single datapoint or a comparison
    """
    comparison_keywords = ["versus", "vs", "compare", "comparison", "difference", "between", "against"]
    trend_keywords = ["trend", "over time", "history", "historical", "graph", "plot", "chart"]
    
    query_lower = query_text.lower()
    
    # Check for comparison keywords
    if any(keyword in query_lower for keyword in comparison_keywords):
        return "comparison"
    # Check for trend keywords
    elif any(keyword in query_lower for keyword in trend_keywords):
        return "trend"
    # Otherwise assume it's a single datapoint query
    else:
        return "single"

# Mapping of common indicators to FRED series patterns
indicator_mapping = {
    "unemployment": {
        "us": "UNRATE",
        "state_pattern": "{code}UR"
    },
    "gdp": {
        "us": "GDP",
        "state_pattern": "{code}RGSP"
    },
    "inflation": {
        "us": "CPIAUCSL",
        "state_pattern": None  # Not available at state level
    },
    "housing": {
        "us": "USSTHPI",
        "state_pattern": "{code}HPI"
    },
    "population": {
        "us": "POPTHM",
        "state_pattern": "{code}POP"
    }
}

# State code mapping
state_codes = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY', 'district of columbia': 'DC', 'puerto rico': 'PR'
}

class SingleDatapointInput(BaseModel):
    indicator: str = Field(description="Economic indicator (unemployment, gdp, inflation, etc.)")
    location: str = Field(description="State, county or US")
    time_period: Optional[str] = Field(default="latest", description="Time period like 'latest', '2022', 'Q3 2023', etc.")
    visualize: Optional[bool] = Field(default=False, description="Whether to create a visualization for this single datapoint")

def get_single_datapoint(indicator: str, location: str, time_period: str = "latest", visualize: bool = False):
    """
    Get a single economic datapoint for a specific indicator, location and time
    Parameter visualize controls whether to create a visualization for this single datapoint
    """
    try:
        # Normalize indicator and location
        indicator_lower = indicator.lower()
        location_lower = location.lower()
        
        # Find the appropriate series ID
        series_id = None
        
        # Handle US national data
        if location_lower in ["us", "united states", "usa", "national", "america"]:
            for key, mapping in indicator_mapping.items():
                if key in indicator_lower or indicator_lower in key:
                    series_id = mapping["us"]
                    break
                    
        # Handle state data
        elif location_lower in state_codes:
            state_code = state_codes[location_lower]
            for key, mapping in indicator_mapping.items():
                if (key in indicator_lower or indicator_lower in key) and mapping["state_pattern"]:
                    series_id = mapping["state_pattern"].format(code=state_code)
                    break
        
        # If no series ID found, try a search
        if not series_id:
            search_term = f"{location} {indicator}"
            results = fred.search(search_term, limit=1)
            if not results.empty:
                series_id = results.iloc[0]["id"]
            else:
                return f"Could not find data for {indicator} in {location}."
        
        # Get the data
        if time_period.lower() == "latest":
            # Get the most recent data point
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            data = fred.get_series(series_id, start_date, end_date)
            if data.empty:
                return f"No data available for {indicator} in {location}."
            
            latest_value = data.iloc[-1]
            latest_date = data.index[-1].strftime("%B %d, %Y")
            
            # Get series info for formatting
            series_info = fred.get_series_info(series_id)
            units = series_info.get('units', '')
            title = series_info.get('title', series_id)
            
            # Only create visualization if requested
            if visualize:
                create_snapshot_visualization(series_id, title, latest_value, data.iloc[-5:], units)
            
            # Return formatted result
            if "percent" in units.lower() or "%" in units:
                return f"The {title} for {location.title()} was {latest_value:.1f}% as of {latest_date}."
            else:
                return f"The {title} for {location.title()} was {latest_value:,.1f} {units} as of {latest_date}."
        
        else:
            # Handle specific time period
            # For simplicity, we'll just search for the closest date
            # This could be expanded to handle quarters, years, etc.
            
            # Try to parse the time period
            try:
                if len(time_period) == 4 and time_period.isdigit():  # Year only
                    start_date = f"{time_period}-01-01"
                    end_date = f"{time_period}-12-31"
                else:
                    # Try to parse as a date
                    parsed_date = pd.to_datetime(time_period)
                    start_date = (parsed_date - timedelta(days=30)).strftime("%Y-%m-%d")
                    end_date = (parsed_date + timedelta(days=30)).strftime("%Y-%m-%d")
            except:
                return f"Could not parse time period: {time_period}. Please use a format like '2022' or 'Q3 2023'."
            
            # Get the data for the specified period
            data = fred.get_series(series_id, start_date, end_date)
            if data.empty:
                return f"No data available for {indicator} in {location} during {time_period}."
            
            # Get the value closest to the specified period
            value = data.iloc[0]  # Default to first value
            date_str = data.index[0].strftime("%B %d, %Y")
            
            # Get series info for formatting
            series_info = fred.get_series_info(series_id)
            units = series_info.get('units', '')
            title = series_info.get('title', series_id)
            
            # Only create visualization if requested
            if visualize:
                create_snapshot_visualization(series_id, title, value, data, units)
            
            # Return formatted result
            if "percent" in units.lower() or "%" in units:
                return f"The {title} for {location.title()} was {value:.1f}% as of {date_str}."
            else:
                return f"The {title} for {location.title()} was {value:,.1f} {units} as of {date_str}."
    
    except Exception as e:
        return f"Error retrieving single datapoint: {str(e)}"

def create_snapshot_visualization(series_id, title, value, trend_data, units=""):
    """
    Creates an attractive single-value visualization with a trend indicator
    """
    try:
        # Create a figure with two subplots - one for the big number, one for the trend
        fig = plt.figure(figsize=(10, 6))
        
        # Create a 2x1 grid, with the big number taking up most of the space
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.1)
        
        # Set up the big number display
        ax_main = fig.add_subplot(gs[0])
        ax_trend = fig.add_subplot(gs[1])
        
        # Remove axis elements from the main display
        ax_main.set_xticks([])
        ax_main.set_yticks([])
        ax_main.spines['top'].set_visible(False)
        ax_main.spines['right'].set_visible(False)
        ax_main.spines['bottom'].set_visible(False)
        ax_main.spines['left'].set_visible(False)
        
        # Add the title
        ax_main.text(0.5, 0.9, title, ha='center', va='center', fontsize=16, fontweight='bold')
        
        # Format the value
        if "percent" in units.lower() or "%" in units:
            value_text = f"{value:.1f}%"
        elif value >= 1_000_000:
            value_text = f"{value/1_000_000:.1f}M {units}"
        elif value >= 1_000:
            value_text = f"{value/1_000:.1f}K {units}"
        else:
            value_text = f"{value:.1f} {units}"
        
        # Add the big number
        ax_main.text(0.5, 0.5, value_text, ha='center', va='center', fontsize=32, fontweight='bold')
        
        # Add the date of the value
        latest_date = trend_data.index[-1].strftime("%B %d, %Y")
        ax_main.text(0.5, 0.2, f"as of {latest_date}", ha='center', va='center', fontsize=12, color='gray')
        
        # Plot the trend
        ax_trend.plot(trend_data.index, trend_data.values, color='#1f77b4', linewidth=2)
        
        # Remove most elements from the trend plot
        ax_trend.spines['top'].set_visible(False)
        ax_trend.spines['right'].set_visible(False)
        ax_trend.set_xticks([])
        
        # Only show min/max on y-axis
        ax_trend.set_yticks([trend_data.min(), trend_data.max()])
        ax_trend.tick_params(axis='y', labelsize=8)
        
        # Add "Trend" label
        ax_trend.set_ylabel("Trend", fontsize=10)
        
        # Store the figure in session state for Streamlit to display
        st.session_state['current_figure'] = fig
        
        return "Visualization created."
    
    except Exception as e:
        return f"Error creating snapshot visualization: {str(e)}"

class TimeComparisonInput(BaseModel):
    indicator: str = Field(description="Economic indicator (unemployment, gdp, etc.)")
    location: str = Field(description="State, county or US")
    period1: str = Field(description="First time period (e.g. '2019', 'Q1 2020')")
    period2: str = Field(description="Second time period (e.g. '2023', 'Q3 2022')")

def compare_time_periods(indicator: str, location: str, period1: str, period2: str):
    """
    Compare economic data between two different time periods
    """
    try:
        # Normalize indicator and location
        indicator_lower = indicator.lower()
        location_lower = location.lower()
        
        # Find the appropriate series ID
        series_id = None
        
        # Handle US national data
        if location_lower in ["us", "united states", "usa", "national", "america"]:
            for key, mapping in indicator_mapping.items():
                if key in indicator_lower or indicator_lower in key:
                    series_id = mapping["us"]
                    break
                    
        # Handle state data
        elif location_lower in state_codes:
            state_code = state_codes[location_lower]
            for key, mapping in indicator_mapping.items():
                if (key in indicator_lower or indicator_lower in key) and mapping["state_pattern"]:
                    series_id = mapping["state_pattern"].format(code=state_code)
                    break
        
        # If no series ID found, try a search
        if not series_id:
            search_term = f"{location} {indicator}"
            results = fred.search(search_term, limit=1)
            if not results.empty:
                series_id = results.iloc[0]["id"]
            else:
                return f"Could not find data for {indicator} in {location}."
        
        # Try to parse the time periods
        try:
            if len(period1) == 4 and period1.isdigit():  # Year only
                start_date1 = f"{period1}-01-01"
                end_date1 = f"{period1}-12-31"
            else:
                # Try to parse as a date
                parsed_date1 = pd.to_datetime(period1)
                start_date1 = (parsed_date1 - timedelta(days=30)).strftime("%Y-%m-%d")
                end_date1 = (parsed_date1 + timedelta(days=30)).strftime("%Y-%m-%d")
                
            if len(period2) == 4 and period2.isdigit():  # Year only
                start_date2 = f"{period2}-01-01"
                end_date2 = f"{period2}-12-31"
            else:
                # Try to parse as a date
                parsed_date2 = pd.to_datetime(period2)
                start_date2 = (parsed_date2 - timedelta(days=30)).strftime("%Y-%m-%d")
                end_date2 = (parsed_date2 + timedelta(days=30)).strftime("%Y-%m-%d")
        except:
            return f"Could not parse time periods: {period1} and {period2}. Please use formats like '2022' or 'Q3 2023'."
        
        # Get the data for both periods
        data1 = fred.get_series(series_id, start_date1, end_date1)
        data2 = fred.get_series(series_id, start_date2, end_date2)
        
        if data1.empty or data2.empty:
            if data1.empty and data2.empty:
                return f"No data available for {indicator} in {location} during {period1} or {period2}."
            elif data1.empty:
                return f"No data available for {indicator} in {location} during {period1}."
            else:
                return f"No data available for {indicator} in {location} during {period2}."
        
        # Get representative values for each period
        # For simplicity, we'll use the average value in each period
        value1 = data1.mean()
        value2 = data2.mean()
        
        # Calculate the percent change
        percent_change = ((value2 - value1) / value1) * 100
        
        # Get series info for formatting
        series_info = fred.get_series_info(series_id)
        units = series_info.get('units', '')
        title = series_info.get('title', series_id)
        
        # Create visualization comparing the two periods
        create_time_comparison_viz(series_id, title, period1, period2, value1, value2, percent_change, units)
        
        # Format the values for display
        if "percent" in units.lower() or "%" in units:
            value1_str = f"{value1:.1f}%"
            value2_str = f"{value2:.1f}%"
            change_str = f"{percent_change:.1f} percentage points"
        else:
            value1_str = f"{value1:,.1f} {units}"
            value2_str = f"{value2:,.1f} {units}"
            change_str = f"{percent_change:.1f}%"
        
        # Return formatted result
        response = f"# {title} in {location.title()}: {period1} vs {period2}\n\n"
        response += f"- {period1}: {value1_str}\n"
        response += f"- {period2}: {value2_str}\n\n"
        
        if percent_change > 0:
            response += f"This represents an increase of {change_str} from {period1} to {period2}."
        elif percent_change < 0:
            response += f"This represents a decrease of {change_str} from {period1} to {period2}."
        else:
            response += f"There was no change between {period1} and {period2}."
        
        return response
    
    except Exception as e:
        return f"Error comparing time periods: {str(e)}"

def create_time_comparison_viz(series_id, title, period1, period2, value1, value2, percent_change, units=""):
    """
    Creates a visualization comparing two time periods
    """
    try:
        # Create the figure
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Define bar positions and width
        positions = [0, 1]
        bar_width = 0.6
        
        # Create the bars
        bars = ax.bar(positions, [value1, value2], width=bar_width)
        
        # Color the bars based on the direction of change
        if percent_change > 0:
            bars[1].set_color('#2ca02c')  # Green for increase
        elif percent_change < 0:
            bars[1].set_color('#d62728')  # Red for decrease
        
        # Remove top and right spines
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # Set title and labels
        ax.set_title(f"{title}: {period1} vs {period2}", fontsize=16, pad=20)
        ax.set_ylabel(units, fontsize=12)
        
        # Set x-axis ticks and labels
        ax.set_xticks(positions)
        ax.set_xticklabels([period1, period2], fontsize=12)
        
        # Add value labels on top of bars
        for i, bar in enumerate(bars):
            height = bar.get_height()
            if "percent" in units.lower() or "%" in units:
                label = f"{height:.1f}%"
            else:
                label = f"{height:,.1f}"
            ax.text(bar.get_x() + bar.get_width()/2, height + (ax.get_ylim()[1] * 0.01),
                   label, ha='center', va='bottom', fontsize=12)
        
        # Add percent change arrow and text
        arrow_props = dict(arrowstyle='->', linewidth=2)
        if percent_change != 0:
            mid_height = (value1 + value2) / 2
            ax.annotate('', xy=(1, mid_height), xytext=(0, mid_height),
                       arrowprops=arrow_props)
            
            # Position the text above or below the arrow based on change direction
            if percent_change > 0:
                y_pos = mid_height + (ax.get_ylim()[1] * 0.05)
                vert_align = 'bottom'
                change_text = f"+{percent_change:.1f}%"
                color = '#2ca02c'
            else:
                y_pos = mid_height - (ax.get_ylim()[1] * 0.05)
                vert_align = 'top'
                change_text = f"{percent_change:.1f}%"
                color = '#d62728'
                
            ax.text(0.5, y_pos, change_text, ha='center', va=vert_align, 
                   fontsize=14, fontweight='bold', color=color)
        
        # Add source annotation
        plt.figtext(0.99, 0.01, f"Source: FRED, Federal Reserve Bank of St. Louis", 
                    ha='right', fontsize=8, fontstyle='italic', color='gray')
        
        # Store the figure in session state for Streamlit to display
        st.session_state['current_figure'] = fig
        
        return "Visualization created."
    
    except Exception as e:
        return f"Error creating time comparison visualization: {str(e)}"

# Create LangChain tool objects
query_classifier_tool = StructuredTool.from_function(
    func=classify_query_type,
    name="classify_query_type",
    description="Determine if a user query is for a single datapoint, trend over time, or comparison"
)

single_datapoint_tool = StructuredTool.from_function(
    func=get_single_datapoint,
    name="get_single_datapoint",
    description="Get a single economic datapoint for a specific indicator, location and time, with optional visualization",
    args_schema=SingleDatapointInput
)

time_comparison_tool = StructuredTool.from_function(
    func=compare_time_periods,
    name="compare_time_periods",
    description="Compare economic data between two different time periods",
    args_schema=TimeComparisonInput
)

# List of all enhanced tools
enhanced_tools = [
    query_classifier_tool,
    single_datapoint_tool,
    time_comparison_tool
]