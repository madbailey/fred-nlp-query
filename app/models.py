# app/models.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import date # Example, if you choose to use date objects

class FredSeriesInfo(BaseModel):
    id: str
    title: str
    units: str
    frequency: Optional[str] = None
    seasonal_adjustment: Optional[str] = None
    seasonal_adjustment_short: Optional[str] = None # a common field from FRED
    notes: Optional[str] = None
    popularity: Optional[int] = None
    observation_start: Optional[str] = None
    observation_end: Optional[str] = None
    last_updated: Optional[str] = None # a common field from FRED
    # real_time_start and real_time_end are often present but might not be needed for typical use cases
    # Add any other fields that are consistently available and useful from FRED series info

class FredDataPoint(BaseModel):
    date: str # Using string for simplicity, can be datetime.date
    value: float

class FredSeriesData(BaseModel): # This represents raw-ish data fetched for a series
    series_id: str
    info: FredSeriesInfo # Store key details from the FRED API
    data: List[FredDataPoint]

class QueryDetails(BaseModel):
    raw_query: str
    query_type: Literal[
        "single_datapoint", 
        "trend_over_time", 
        "geographical_comparison", 
        "time_comparison", 
        "series_search",
        "data_retrieval", # For direct requests like "get GDP for US"
        "unknown"
    ] = "unknown"
    indicators: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    time_periods: List[str] = Field(default_factory=list) # e.g., ["latest", "2022-01-01 to 2023-01-01"]
    parameters: Dict[str, Any] = Field(default_factory=dict) # e.g., normalize: True, state1: "CA"
    visualization_request: Optional[str] = None # e.g., "line_chart showing GDP for California"

# Renamed from FredSeriesData in the prompt to ProcessedDataset as per the example structure provided
class ProcessedDataset(BaseModel): 
    id: str # Could be original series_id or a generated one for comparisons
    name: str # User-friendly name
    data_points: List[FredDataPoint]
    metadata: Dict[str, Any] = Field(default_factory=dict) # Store units, frequency, notes etc. from FredSeriesInfo

class ProcessedData(BaseModel):
    query_details: QueryDetails
    datasets: List[ProcessedDataset] # A list of datasets involved in the query
    summary_text: Optional[str] = None # e.g., "GDP for California grew by X%"
    # Include fields for specific analysis results if needed, e.g.,
    # growth_rates: Optional[Dict[str, float]] = None
    # comparison_metrics: Optional[Dict[str, Any]] = None

class VisualizationSpec(BaseModel):
    chart_type: Literal[
        "line_chart", 
        "bar_chart", 
        "multi_line_chart", 
        "comparison_bar_chart", 
        "snapshot_value_display" # For single datapoint with a small trend
    ]
    title: str
    data_ids: List[str] # Refers to ProcessedDataset.id to fetch data for plotting
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict) # e.g., colors, recession_shading: True

class OrchestratorResponse(BaseModel):
    query_details: QueryDetails
    processed_data: Optional[ProcessedData] = None
    visualization_spec: Optional[VisualizationSpec] = None # Visualization layer will take this
    # The actual figure object is not part of the model, it's an artifact passed to Streamlit
    textual_response: str # Primary response for the LLM / user
    error_message: Optional[str] = None

# Ensure Pydantic is listed in requirements.txt
# Ensure python-dotenv is listed in requirements.txt (for FRED_API_KEY example in FredService)
# Ensure fredapi is listed in requirements.txt
# Ensure streamlit is listed in requirements.txt (for caching)
# Ensure pandas is listed in requirements.txt
