# app/logic/orchestrator.py
import logging
from typing import Optional, List, Dict, Any
import os

# Services
from app.services.fred_service import FredService
from app.logic.query_understanding import QueryUnderstandingService
from app.logic.data_retrieval import DataRetrievalService
from app.logic.data_processing import DataProcessingService
from app.visualization.plot_service import PlottingService

# Models
from app.models import (
    QueryDetails, FredSeriesData, ProcessedData, ProcessedDataset, 
    VisualizationSpec, OrchestratorResponse, FredSeriesInfo, FredDataPoint
)

logger = logging.getLogger(__name__)

class OrchestratorService:
    def __init__(self, fred_api_key: Optional[str] = None): # fred_api_key param is not strictly needed here
        self.fred_service = FredService() 
        self.query_understanding_service = QueryUnderstandingService()
        self.data_retrieval_service = DataRetrievalService(self.fred_service)
        self.data_processing_service = DataProcessingService()
        self.plotting_service = PlottingService(self.fred_service)
        logger.info("OrchestratorService initialized with all services.")

    def _get_series_id_from_query(self, indicator: str, location: str) -> Optional[str]:
        # Placeholder - to be implemented
        # This would involve more sophisticated logic, possibly using a pre-defined mapping,
        # or performing a targeted search using DataRetrievalService.search_series
        # and then filtering/ranking results.
        logger.info(f"Attempting to find series ID for indicator '{indicator}' in location '{location}'")
        
        # Attempt direct common series IDs for US
        if location.upper() == "US":
            if "gdp" in indicator.lower() and ("real" in indicator.lower() or "rgdp" in indicator.lower()):
                logger.info("Identified as US Real GDP, using GDPC1.")
                return "GDPC1"
            elif "gdp" in indicator.lower(): # Nominal GDP
                logger.info("Identified as US Nominal GDP, using GDP.")
                return "GDP"
            elif "cpi" in indicator.lower() or "inflation" in indicator.lower():
                logger.info("Identified as US CPI/Inflation, using CPIAUCSL.")
                return "CPIAUCSL"
            elif "unemployment" in indicator.lower() or "unemployment rate" in indicator.lower():
                logger.info("Identified as US Unemployment Rate, using UNRATE.")
                return "UNRATE"
            elif "nonfarm payrolls" in indicator.lower() or "nfp" in indicator.lower():
                logger.info("Identified as US Nonfarm Payrolls, using PAYEMS.")
                return "PAYEMS"
            # Add more common US series IDs here if needed
        
        # General search if not a common US series or for other locations
        search_term = f"{indicator} {location}"
        logger.info(f"Performing FRED search for: '{search_term}'")
        search_results: List[FredSeriesInfo] = self.data_retrieval_service.search_series(search_term, limit=1)
        
        if search_results:
            series_id = search_results[0].id
            logger.info(f"Found series ID '{series_id}' for search term '{search_term}'")
            return series_id
        else:
            # Fallback: try indicator only for US if location was US and specific search failed
            if location.upper() == "US":
                logger.info(f"Search for '{search_term}' failed. Trying indicator '{indicator}' alone for US as fallback.")
                search_results_fb: List[FredSeriesInfo] = self.data_retrieval_service.search_series(indicator, limit=1)
                if search_results_fb:
                    series_id_fb = search_results_fb[0].id
                    logger.info(f"Found series ID '{series_id_fb}' using fallback search for indicator '{indicator}' (US).")
                    return series_id_fb
            
            logger.warning(f"No series ID found for indicator: '{indicator}', location: '{location}' after all attempts.")
            return None

    def handle_query(self, raw_query: str) -> OrchestratorResponse:
        logger.info(f"Orchestrator handling query: {raw_query}")
        query_details = QueryDetails(raw_query=raw_query, query_type="unknown") # Default for error cases before parsing
        
        try:
            query_details = self.query_understanding_service.parse_query(raw_query)
            logger.debug(f"Parsed query details: {query_details}")

            textual_response = ""
            processed_data_obj: Optional[ProcessedData] = None
            visualization_figure: Optional[Any] = None 

            # --- Handle Series Search ---
            if query_details.query_type == "series_search":
                search_term = query_details.raw_query # Default to raw query for search
                # Try to be more specific if query understanding extracted terms
                if query_details.indicators:
                    search_term = query_details.indicators[0]
                    if query_details.locations:
                        search_term = f"{query_details.indicators[0]} for {query_details.locations[0]}"
                
                logger.info(f"Performing series search for: '{search_term}'")
                search_results = self.data_retrieval_service.search_series(search_term, limit=5)
                if search_results:
                    textual_response = "Found the following series based on your search:\n"
                    for item in search_results:
                        textual_response += f"- **ID:** {item.id}, **Title:** {item.title} (Popularity: {item.popularity})\n"
                else:
                    textual_response = f"No series found matching your search term: '{search_term}'."
                
                return OrchestratorResponse(query_details=query_details, textual_response=textual_response)

            # --- Handle Data Retrieval, Processing, and Visualization for other query types ---
            elif query_details.query_type in ["data_retrieval", "single_datapoint", "trend_over_time", "geographical_comparison"]:
                series_to_process_params: List[Dict[str, str]] = [] # List of {'indicator': name, 'location': name}

                if query_details.query_type == "geographical_comparison" and len(query_details.locations) > 1 and query_details.indicators:
                    indicator_name = query_details.indicators[0] # Compare one indicator across multiple locations
                    for loc_name in query_details.locations:
                        series_to_process_params.append({"indicator": indicator_name, "location": loc_name})
                elif query_details.indicators and query_details.locations: # Single series or first in list for other types
                     series_to_process_params.append({"indicator": query_details.indicators[0], "location": query_details.locations[0]})
                else: # Not enough info
                    textual_response = "I need an indicator (like 'GDP') and a location (like 'US' or a state name) to fetch data."
                    if not query_details.indicators: textual_response += " Indicator missing."
                    if not query_details.locations: textual_response += " Location missing."
                    return OrchestratorResponse(query_details=query_details, textual_response=textual_response, error_message="Insufficient information for data retrieval.")

                fetched_series_data_map: Dict[str, FredSeriesData] = {} # Keyed by series_id
                for params in series_to_process_params:
                    series_id = self._get_series_id_from_query(params["indicator"], params["location"])
                    if not series_id:
                        textual_response += f"\nCould not find a series ID for '{params['indicator']}' in '{params['location']}'."
                        continue 
                    
                    # Determine time period (simplified)
                    start_date, end_date = None, None 
                    if query_details.time_periods and query_details.time_periods[0] != "latest":
                        tp = query_details.time_periods[0] # Using first identified period
                        if " to " in tp: parts = tp.split(" to "); start_date, end_date = parts[0].strip(), parts[1].strip()
                        elif len(tp) == 4 and tp.isdigit(): start_date = f"{tp}-01-01"; end_date = f"{tp}-12-31" # Year
                        else: start_date = tp # Assume YYYY-MM-DD or similar
                    
                    logger.info(f"Fetching data for series ID: {series_id} ('{params['indicator']}' for '{params['location']}'). Dates: {start_date} to {end_date}")
                    series_data = self.data_retrieval_service.get_series_data(series_id, start_date=start_date, end_date=end_date)
                    
                    if series_data and series_data.data:
                        fetched_series_data_map[series_id] = series_data
                        textual_response += f"\nSuccessfully retrieved {len(series_data.data)} data points for '{series_data.info.title}'."
                    else:
                        textual_response += f"\nNo data found for '{params['indicator']}' in '{params['location']}' (Series ID: {series_id})."

                if not fetched_series_data_map:
                    final_text = textual_response if textual_response else "No data could be retrieved for any specified series."
                    return OrchestratorResponse(query_details=query_details, textual_response=final_text, error_message=final_text)

                # Prepare datasets for processing and plotting
                datasets_for_plotting: List[ProcessedDataset] = []
                for s_id, s_data in fetched_series_data_map.items():
                    datasets_for_plotting.append(ProcessedDataset(
                        id=s_id, name=s_data.info.title or s_id,
                        data_points=s_data.data, metadata=s_data.info.model_dump()
                    ))
                
                # --- Apply Normalization if requested for comparison ---
                is_normalized_for_plot = False
                if query_details.parameters.get("normalize", False) and len(datasets_for_plotting) > 1:
                    logger.info("Normalization requested for multiple series. Applying...")
                    normalized_plot_datasets_temp: List[ProcessedDataset] = []
                    for original_dataset in datasets_for_plotting: # Iterate over copies from fetched_series_data_map values
                        # We need FredSeriesData for normalize_series, so get it from fetched_series_data_map
                        original_fred_series_data = fetched_series_data_map.get(original_dataset.id)
                        if original_fred_series_data:
                            normalized_ds = self.data_processing_service.normalize_series(original_fred_series_data)
                            if normalized_ds.metadata.get("status") == "success":
                                normalized_plot_datasets_temp.append(normalized_ds)
                                logger.info(f"Successfully normalized series {original_dataset.id} for plotting.")
                            else: # Normalization failed, use original
                                normalized_plot_datasets_temp.append(original_dataset)
                                logger.warning(f"Normalization failed for {original_dataset.id}, using original data for plot.")
                        else: # Should not happen if datasets_for_plotting is derived from fetched_series_data_map
                             normalized_plot_datasets_temp.append(original_dataset)
                    datasets_for_plotting = normalized_plot_datasets_temp
                    textual_response += "\nData has been normalized for comparison plotting."
                    is_normalized_for_plot = True

                # --- Create ProcessedData object ---
                processed_data_obj = ProcessedData(
                    query_details=query_details,
                    datasets=datasets_for_plotting, 
                    summary_text=textual_response.strip()
                )
                
                # --- Generate Visualization if requested ---
                if query_details.visualization_request and processed_data_obj and processed_data_obj.datasets:
                    logger.info(f"Visualization requested: {query_details.visualization_request}")
                    
                    chart_type = "line_chart" # Default
                    if query_details.visualization_request == "comparison_bar_chart": chart_type = "comparison_bar_chart" # Placeholder
                    # Add more mappings if needed: e.g. snapshot_value_display
                    
                    plot_title = query_details.indicators[0] if query_details.indicators else "Economic Data"
                    if query_details.locations: plot_title += f" for {', '.join(query_details.locations)}"
                    if is_normalized_for_plot: plot_title += " (Normalized)"

                    y_axis_label = datasets_for_plotting[0].metadata.get("units", "Value")
                    if is_normalized_for_plot:
                        # If normalized, units change to an index.
                        # The normalize_series method stores this in ProcessedDataset.metadata.normalized_units
                        y_axis_label = datasets_for_plotting[0].metadata.get("normalized_units", "Index (Normalized)")


                    vis_spec = VisualizationSpec(
                        chart_type=chart_type, title=plot_title,
                        data_ids=[ds.id for ds in processed_data_obj.datasets], # IDs of datasets in ProcessedData
                        y_axis_label=y_axis_label,
                        options={
                            "recession_shading": query_details.parameters.get("recession_shading", True), 
                            "default_source_text": True,
                            "normalize_status": is_normalized_for_plot # Pass normalization status for context
                        }
                    )
                    
                    if chart_type == "line_chart": # Currently only line_chart is fully implemented in PlottingService
                        visualization_figure = self.plotting_service.create_line_chart(
                            datasets=processed_data_obj.datasets, # Pass the (potentially normalized) datasets
                            spec=vis_spec
                        )
                        logger.info(f"Line chart created: {visualization_figure}")
                        if visualization_figure: textual_response += "\nA chart has been generated and is available for display."
                
            else: # Unhandled query type
                textual_response = "I'm not sure how to handle that query. You can try searching for series (e.g., 'search for US GDP'), or asking for data for a specific indicator and location (e.g., 'US GDP trend over last 5 years')."
                return OrchestratorResponse(query_details=query_details, textual_response=textual_response, error_message="Unhandled query type by orchestrator.")

            return OrchestratorResponse(
                query_details=query_details, 
                processed_data=processed_data_obj,
                visualization_figure=visualization_figure, # This should be visualization_spec, not figure
                textual_response=textual_response.strip()
            )

        except Exception as e:
            logger.error(f"Unhandled error in orchestrator handle_query: {e}", exc_info=True)
            # Ensure query_details is always populated, even if it's the default one
            return OrchestratorResponse(
                query_details=query_details, # This will be the one from beginning of try or after parsing
                error_message=f"An unexpected error occurred: {str(e)}",
                textual_response=f"I'm sorry, but I encountered an unexpected error while processing your request: {str(e)}"
            )

if __name__ == '__main__':
    if os.getenv("FRED_API_KEY"):
        try:
            orchestrator = OrchestratorService()
            
            test_queries = [
                "Search for housing price index series",
                "What is the latest GDP for US?",
                "Plot US unemployment rate for the last 10 years",
                "Compare GDP for CA and TX, normalized",
                "GDP for California",
                "Nonfarm Payrolls US",
                "Show me a graph of GDPC1 data from 2020 to 2022 with recession shading"
            ]

            for test_query in test_queries:
                print(f"\n--- Testing Query: \"{test_query}\" ---")
                response = orchestrator.handle_query(test_query)
                print(f"Raw Query: {response.query_details.raw_query}")
                print(f"  Query Type: {response.query_details.query_type}")
                print(f"  Indicators: {response.query_details.indicators}")
                print(f"  Locations: {response.query_details.locations}")
                print(f"  Time Periods: {response.query_details.time_periods}")
                print(f"  Params: {response.query_details.parameters}")
                print(f"  Visualization Request: {response.query_details.visualization_request}")
                print(f"Textual Response: \n{response.textual_response}")
                if response.processed_data and response.processed_data.datasets:
                    print(f"  Processed Datasets ({len(response.processed_data.datasets)}):")
                    for ds in response.processed_data.datasets:
                        print(f"    - ID: {ds.id}, Name: {ds.name}, Points: {len(ds.data_points)}")
                        if ds.metadata.get("status") == "normalization_failed":
                            print(f"      Normalization failed: {ds.metadata.get('reason')}")
                        elif ds.metadata.get("normalized_units"):
                            print(f"      Normalized Units: {ds.metadata.get('normalized_units')}")


                if response.visualization_figure: # In Streamlit, this would be st.pyplot(response.visualization_figure)
                    print(f"  Visualization Figure: Generated (type: {type(response.visualization_figure)})")
                    # response.visualization_figure.savefig(f"test_plot_{test_query.replace(' ', '_')[:20]}.png")
                    # print("  (Plot saved for review)")
                
                if response.error_message: 
                    print(f"  Error Message: {response.error_message}")
                print("-" * 30)
        
        except ValueError as ve:
            print(f"ValueError during OrchestratorService initialization or use: {ve}")
        except Exception as e:
            print(f"An unexpected error occurred during testing '{test_query}': {e}", exc_info=True)
    else:
        print("FRED_API_KEY not set. Skipping OrchestratorService example usage.")
