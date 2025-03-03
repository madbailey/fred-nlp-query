from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from fredapi import Fred
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime, timedelta
import streamlit as st
import matplotlib as mpl
from matplotlib.ticker import FuncFormatter

# Configure Matplotlib for better aesthetics
plt.style.use('seaborn-v0_8-whitegrid')
mpl.rcParams['font.family'] = 'sans-serif'
mpl.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
mpl.rcParams['axes.labelsize'] = 11
mpl.rcParams['axes.titlesize'] = 14
mpl.rcParams['xtick.labelsize'] = 10
mpl.rcParams['ytick.labelsize'] = 10

# Initialize FRED API
fred = Fred(api_key=os.getenv("FRED_API_KEY"))

# Input schemas for composite tools
class StateGDPComparisonInput(BaseModel):
    state1: str = Field(description="First state name (e.g., 'California', 'Texas')")
    state2: str = Field(description="Second state name (e.g., 'New York', 'Florida')")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(default=None, description="End date in YYYY-MM-DD format")
    normalize: Optional[bool] = Field(default=True, description="Whether to normalize data to start_date=100")
    show_growth_rate: Optional[bool] = Field(default=False, description="Also show year-over-year growth rates")

class StatesVsUSComparisonInput(BaseModel):
    states: List[str] = Field(description="List of state names to compare (e.g., ['California', 'Texas'])")
    indicator: str = Field(description="Economic indicator to compare (e.g., 'gdp', 'unemployment', 'housing')")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(default=None, description="End date in YYYY-MM-DD format")
    normalize: Optional[bool] = Field(default=True, description="Whether to normalize data to start_date=100")

# Dictionary of state names to FRED codes
state_codes = {
    'alabama': 'AL',
    'alaska': 'AK',
    'arizona': 'AZ',
    'arkansas': 'AR',
    'california': 'CA',
    'colorado': 'CO',
    'connecticut': 'CT',
    'delaware': 'DE',
    'florida': 'FL',
    'georgia': 'GA',
    'hawaii': 'HI',
    'idaho': 'ID',
    'illinois': 'IL',
    'indiana': 'IN',
    'iowa': 'IA',
    'kansas': 'KS',
    'kentucky': 'KY',
    'louisiana': 'LA',
    'maine': 'ME',
    'maryland': 'MD',
    'massachusetts': 'MA',
    'michigan': 'MI',
    'minnesota': 'MN',
    'mississippi': 'MS',
    'missouri': 'MO',
    'montana': 'MT',
    'nebraska': 'NE',
    'nevada': 'NV',
    'new hampshire': 'NH',
    'new jersey': 'NJ',
    'new mexico': 'NM',
    'new york': 'NY',
    'north carolina': 'NC',
    'north dakota': 'ND',
    'ohio': 'OH',
    'oklahoma': 'OK',
    'oregon': 'OR',
    'pennsylvania': 'PA',
    'rhode island': 'RI',
    'south carolina': 'SC',
    'south dakota': 'SD',
    'tennessee': 'TN',
    'texas': 'TX',
    'utah': 'UT',
    'vermont': 'VT',
    'virginia': 'VA',
    'washington': 'WA',
    'west virginia': 'WV',
    'wisconsin': 'WI',
    'wyoming': 'WY',
    'district of columbia': 'DC',
    'puerto rico': 'PR'
}

# Map of indicator types to their FRED series patterns
indicator_patterns = {
    'gdp': {
        'state_pattern': '{code}RGSP',
        'us_pattern': 'GDPCA',
        'title': 'Real GDP',
        'units': 'Millions of Chained 2017 Dollars'
    },
    'unemployment': {
        'state_pattern': '{code}UR',
        'us_pattern': 'UNRATE',
        'title': 'Unemployment Rate',
        'units': 'Percent'
    },
    'housing': {
        'state_pattern': '{code}HPI',
        'us_pattern': 'USSTHPI',
        'title': 'House Price Index',
        'units': 'Index'
    },
    'nonfarm_payrolls': {
        'state_pattern': '{code}NF',
        'us_pattern': 'PAYEMS',
        'title': 'Nonfarm Payrolls',
        'units': 'Thousands of Persons'
    },
    'personal_income': {
        'state_pattern': '{code}NPCPI',
        'us_pattern': 'DSPIC96',
        'title': 'Personal Income',
        'units': 'Millions of Dollars'
    }
}

# Helper functions from previous implementation
def format_large_number(x, pos):
    """Format large numbers with K, M, B, T suffixes"""
    if x >= 1e12:
        return f'{x/1e12:.1f}T'
    elif x >= 1e9:
        return f'{x/1e9:.1f}B'
    elif x >= 1e6:
        return f'{x/1e6:.1f}M'
    elif x >= 1e3:
        return f'{x/1e3:.1f}K'
    else:
        return f'{x:.1f}'

def highlight_recessions(ax, start_date, end_date):
    """Add recession shading to a matplotlib axis"""
    recessions = fred.get_series('USREC', start_date, end_date)
    if recessions.empty:
        return

    # Find spans where USREC == 1 (indicating recession)
    rec_dates = recessions[recessions == 1].index
    if len(rec_dates) == 0:
        return
        
    # Group consecutive dates
    rec_spans = []
    current_span = [rec_dates[0]]
    
    for i in range(1, len(rec_dates)):
        # If consecutive, add to current span
        if (rec_dates[i] - rec_dates[i-1]).days <= 31:  # Allow for a bit of gap (monthly data)
            current_span.append(rec_dates[i])
        else:
            # Not consecutive, end current span and start a new one
            rec_spans.append((min(current_span), max(current_span)))
            current_span = [rec_dates[i]]
    
    # Add the last span
    if current_span:
        rec_spans.append((min(current_span), max(current_span)))
    
    # Add shading for each recession period
    for rec_start, rec_end in rec_spans:
        ax.axvspan(rec_start, rec_end, alpha=0.2, color='gray', label='Recession')

def normalize_series(series_list, labels):
    """Normalize multiple series to start at 100 for comparison"""
    normalized_series = []
    for series in series_list:
        if not series.empty:
            # Find first non-NaN value
            first_valid = series.first_valid_index()
            if first_valid is not None:
                base_value = series[first_valid]
                if base_value != 0:  # Avoid division by zero
                    normalized_series.append((series / base_value) * 100)
                else:
                    # If base is zero, just add the original
                    normalized_series.append(series)
            else:
                normalized_series.append(series)
        else:
            normalized_series.append(series)
    
    return normalized_series

def calculate_growth_rate(series, period='yoy'):
    """Calculate growth rate for a series"""
    if period == 'yoy':
        growth = series.pct_change(periods=12) * 100
    elif period == 'qoq':
        growth = series.pct_change(periods=3) * 100
    elif period == 'mom':
        growth = series.pct_change(periods=1) * 100
    else:
        growth = series.pct_change() * 100
    
    return growth

def calculate_total_growth(series):
    """Calculate total growth from start to end of series"""
    if series.empty:
        return None
    
    # Get first and last non-NaN values
    first_valid = series.first_valid_index()
    last_valid = series.last_valid_index()
    
    if first_valid is None or last_valid is None:
        return None
    
    first_value = series[first_valid]
    last_value = series[last_valid]
    
    if first_value == 0:
        return None  # Avoid division by zero
    
    total_growth = ((last_value / first_value) - 1) * 100
    years = (last_valid - first_valid).days / 365.25
    
    if years > 0:
        cagr = ((last_value / first_value) ** (1 / years) - 1) * 100
        return total_growth, cagr
    else:
        return total_growth, None

# Composite tool implementations
def compare_state_gdp(state1: str, state2: str, start_date: str, end_date: Optional[str] = None, 
                     normalize: bool = True, show_growth_rate: bool = False):
    """Compare the real GDP between two US states with a comprehensive analysis"""
    try:
        # Set default end date if not provided
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        # Convert state names to codes
        state1_lower = state1.lower()
        state2_lower = state2.lower()
        
        if state1_lower not in state_codes:
            return f"Error: '{state1}' is not a recognized US state."
        if state2_lower not in state_codes:
            return f"Error: '{state2}' is not a recognized US state."
            
        state1_code = state_codes[state1_lower]
        state2_code = state_codes[state2_lower]
        
        # Get FRED series IDs for Real GDP
        series1_id = f"{state1_code}RGSP"
        series2_id = f"{state2_code}RGSP"
        
        # Fetch data from FRED
        data1 = fred.get_series(series1_id, start_date, end_date)
        data2 = fred.get_series(series2_id, start_date, end_date)
        
        # Get series info
        info1 = fred.get_series_info(series1_id)
        info2 = fred.get_series_info(series2_id)
        
        # Store in session state for potential future use
        st.session_state[f"data_{series1_id}"] = data1
        st.session_state[f"info_{series1_id}"] = info1
        st.session_state[f"data_{series2_id}"] = data2
        st.session_state[f"info_{series2_id}"] = info2
        
        # Calculate total and compound growth rates
        growth1 = calculate_total_growth(data1)
        growth2 = calculate_total_growth(data2)
        
        # Create visualization
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Process data for visualization
        if normalize:
            # Normalize to start date = 100
            normalized_data = normalize_series([data1, data2], [state1, state2])
            ax.plot(normalized_data[0].index, normalized_data[0].values, color='#1f77b4', linewidth=2, label=f"{state1}")
            ax.plot(normalized_data[1].index, normalized_data[1].values, color='#ff7f0e', linewidth=2, label=f"{state2}")
            y_label = "Index (Base = 100)"
        else:
            # Use raw values
            ax.plot(data1.index, data1.values, color='#1f77b4', linewidth=2, label=f"{state1}")
            ax.plot(data2.index, data2.values, color='#ff7f0e', linewidth=2, label=f"{state2}")
            y_label = "Real GDP (Millions of Chained 2017 Dollars)"
        
        # Add recession shading
        highlight_recessions(ax, min(data1.index.min(), data2.index.min()), 
                           max(data1.index.max(), data2.index.max()))
        
        # Format the chart
        title = f"Real GDP Comparison: {state1} vs {state2} ({start_date.split('-')[0]} to {end_date.split('-')[0]})"
        ax.set_title(title, fontweight='bold', pad=15)
        ax.set_xlabel('Year', labelpad=10)
        ax.set_ylabel(y_label, labelpad=10)
        
        # Format y-axis for large numbers
        ax.yaxis.set_major_formatter(FuncFormatter(format_large_number))
        
        # Format x-axis dates
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        
        plt.xticks(rotation=45)
        ax.legend(loc='best')
        plt.tight_layout()
        
        # Add source annotation
        plt.figtext(0.99, 0.01, f"Source: FRED, Federal Reserve Bank of St. Louis", 
                    ha='right', fontsize=8, fontstyle='italic', color='gray')
        
        # Store the figure in session state for Streamlit to display
        st.session_state['current_figure'] = fig
        
        # Prepare the analysis response
        response = f"# Real GDP Comparison: {state1} vs {state2}\n\n"
        
        # Add growth analysis
        if growth1 and growth2:
            total_growth1, cagr1 = growth1
            total_growth2, cagr2 = growth2
            
            response += f"## Growth Analysis ({start_date.split('-')[0]} to {end_date.split('-')[0]})\n\n"
            response += f"**{state1}**:\n"
            response += f"- Total Growth: {total_growth1:.2f}%\n"
            if cagr1:
                response += f"- Compound Annual Growth Rate: {cagr1:.2f}%\n\n"
                
            response += f"**{state2}**:\n"
            response += f"- Total Growth: {total_growth2:.2f}%\n"
            if cagr2:
                response += f"- Compound Annual Growth Rate: {cagr2:.2f}%\n\n"
                
            # Determine which state grew faster
            if total_growth1 > total_growth2:
                difference = total_growth1 - total_growth2
                response += f"**{state1}'s economy grew {difference:.2f} percentage points more than {state2}'s over this period.**\n\n"
            elif total_growth2 > total_growth1:
                difference = total_growth2 - total_growth1
                response += f"**{state2}'s economy grew {difference:.2f} percentage points more than {state1}'s over this period.**\n\n"
            else:
                response += "**Both states showed identical growth over this period.**\n\n"
        
        # Add latest data point comparison
        latest1 = data1.iloc[-1] if not data1.empty else None
        latest2 = data2.iloc[-1] if not data2.empty else None
        
        if latest1 is not None and latest2 is not None:
            response += f"## Latest GDP Values ({data1.index[-1].year})\n\n"
            response += f"- {state1}: {latest1:,.0f} million USD\n"
            response += f"- {state2}: {latest2:,.0f} million USD\n\n"
            
            if latest1 > latest2:
                ratio = latest1 / latest2
                response += f"**{state1}'s economy is currently {ratio:.2f}x the size of {state2}'s economy.**\n\n"
            elif latest2 > latest1:
                ratio = latest2 / latest1
                response += f"**{state2}'s economy is currently {ratio:.2f}x the size of {state1}'s economy.**\n\n"
        
        # Add visualization note
        response += "I've created a chart comparing the Real GDP trends of both states. "
        if normalize:
            response += "The data has been normalized to a base of 100 at the start date to better show relative growth."
        
        return response
    except Exception as e:
        return f"Error comparing state GDP: {str(e)}"

def compare_states_vs_us(states: List[str], indicator: str, start_date: str, 
                       end_date: Optional[str] = None, normalize: bool = True):
    """Compare economic indicators for multiple states against the US national average"""
    try:
        # Set default end date if not provided
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        # Check if indicator is supported
        indicator = indicator.lower()
        if indicator not in indicator_patterns:
            supported = ", ".join(indicator_patterns.keys())
            return f"Error: '{indicator}' is not a supported indicator. Supported indicators are: {supported}"
        
        # Get indicator pattern
        pattern = indicator_patterns[indicator]
        
        # Prepare series IDs and labels
        series_ids = []
        labels = []
        state_codes_list = []
        
        for state in states:
            state_lower = state.lower()
            if state_lower not in state_codes:
                return f"Error: '{state}' is not a recognized US state."
                
            state_code = state_codes[state_lower]
            state_codes_list.append(state_code)
            
            # Create series ID from pattern
            series_id = pattern['state_pattern'].format(code=state_code)
            series_ids.append(series_id)
            labels.append(state)
        
        # Add US national series
        us_series_id = pattern['us_pattern']
        series_ids.append(us_series_id)
        labels.append("United States")
        
        # Fetch data from FRED
        all_data = []
        for series_id in series_ids:
            data = fred.get_series(series_id, start_date, end_date)
            all_data.append(data)
            
            # Store in session state
            st.session_state[f"data_{series_id}"] = data
            
            try:
                info = fred.get_series_info(series_id)
                st.session_state[f"info_{series_id}"] = info
            except:
                # Some series might not have detailed info
                pass
        
        # Calculate growth rates
        growth_rates = []
        for data in all_data:
            growth = calculate_total_growth(data)
            growth_rates.append(growth)
        
        # Create visualization
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Process data for visualization
        if normalize:
            # Normalize to start date = 100
            normalized_data = normalize_series(all_data, labels)
            for i, (data, label) in enumerate(zip(normalized_data, labels)):
                if label == "United States":
                    # Make US line distinct
                    ax.plot(data.index, data.values, color='black', linewidth=3, linestyle='-', label=label)
                else:
                    ax.plot(data.index, data.values, linewidth=2, label=label)
                    
            y_label = "Index (Base = 100)"
        else:
            # Use raw values
            for i, (data, label) in enumerate(zip(all_data, labels)):
                if label == "United States":
                    # Make US line distinct
                    ax.plot(data.index, data.values, color='black', linewidth=3, linestyle='-', label=label)
                else:
                    ax.plot(data.index, data.values, linewidth=2, label=label)
                    
            y_label = pattern['units']
        
        # Add recession shading
        # Find the earliest and latest dates across all series
        all_dates = []
        for data in all_data:
            if not data.empty:
                all_dates.extend(data.index)
                
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            highlight_recessions(ax, min_date, max_date)
        
        # Format the chart
        title = f"{pattern['title']} Comparison: {', '.join(states)} vs US"
        ax.set_title(title, fontweight='bold', pad=15)
        ax.set_xlabel('Date', labelpad=10)
        ax.set_ylabel(y_label, labelpad=10)
        
        # Format y-axis for large numbers
        ax.yaxis.set_major_formatter(FuncFormatter(format_large_number))
        
        # Format x-axis dates
        if all_dates:
            date_range = max_date - min_date
            
            if date_range.days > 365 * 5:
                # For long time periods, show years
                ax.xaxis.set_major_locator(mdates.YearLocator(2))
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
            elif date_range.days > 365:
                # For medium time periods, show quarters
                ax.xaxis.set_major_locator(mdates.MonthLocator([1, 4, 7, 10]))
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
            else:
                # For short time periods, show months
                ax.xaxis.set_major_locator(mdates.MonthLocator())
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        
        plt.xticks(rotation=45)
        
        # Add legend - position it outside if there are many series
        if len(series_ids) > 4:
            ax.legend(loc='upper left', bbox_to_anchor=(1.05, 1), borderaxespad=0.)
        else:
            ax.legend(loc='best')
        
        plt.tight_layout()
        
        # Add source annotation
        plt.figtext(0.99, 0.01, f"Source: FRED, Federal Reserve Bank of St. Louis", 
                    ha='right', fontsize=8, fontstyle='italic', color='gray')
        
        # Store the figure in session state for Streamlit to display
        st.session_state['current_figure'] = fig
        
        # Prepare the analysis response
        response = f"# {pattern['title']} Comparison: {', '.join(states)} vs United States\n\n"
        
        # Add growth analysis
        response += f"## Growth Analysis ({start_date.split('-')[0]} to {end_date.split('-')[0]})\n\n"
        
        # State growth rates
        for i, (state, growth) in enumerate(zip(labels[:-1], growth_rates[:-1])):
            if growth:
                total_growth, cagr = growth
                response += f"**{state}**:\n"
                response += f"- Total Growth: {total_growth:.2f}%\n"
                if cagr:
                    response += f"- Compound Annual Growth Rate: {cagr:.2f}%\n\n"
        
        # US growth rate
        us_growth = growth_rates[-1]
        if us_growth:
            total_growth_us, cagr_us = us_growth
            response += f"**United States**:\n"
            response += f"- Total Growth: {total_growth_us:.2f}%\n"
            if cagr_us:
                response += f"- Compound Annual Growth Rate: {cagr_us:.2f}%\n\n"
        
        # State vs US comparison
        response += "## Performance Relative to US Average\n\n"
        
        for i, (state, growth) in enumerate(zip(labels[:-1], growth_rates[:-1])):
            if growth and us_growth:
                total_growth_state, _ = growth
                total_growth_us, _ = us_growth
                
                difference = total_growth_state - total_growth_us
                
                if difference > 0:
                    response += f"- {state} outperformed the US average by {abs(difference):.2f} percentage points\n"
                elif difference < 0:
                    response += f"- {state} underperformed the US average by {abs(difference):.2f} percentage points\n"
                else:
                    response += f"- {state} performed exactly at the US average\n"
        
        # Add visualization note
        response += "\nI've created a chart comparing the trends. "
        if normalize:
            response += "The data has been normalized to a base of 100 at the start date to better show relative changes."
        
        return response
    except Exception as e:
        return f"Error comparing states vs US: {str(e)}"

# Create LangChain tool objects for composite tools
state_gdp_comparison_tool = StructuredTool.from_function(
    func=compare_state_gdp,
    name="compare_state_gdp",
    description="Compare real GDP between two US states with detailed analysis and visualization",
    args_schema=StateGDPComparisonInput
)

states_vs_us_tool = StructuredTool.from_function(
    func=compare_states_vs_us,
    name="compare_states_vs_us",
    description="Compare economic indicators for multiple states against the US national average",
    args_schema=StatesVsUSComparisonInput
)

# Export the composite tools
fred_composite_tools = [
    state_gdp_comparison_tool,
    states_vs_us_tool
]