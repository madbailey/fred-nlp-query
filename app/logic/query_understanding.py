# app/logic/query_understanding.py
import re
from typing import List, Dict, Any, Tuple # Tuple not used, can remove
from app.models import QueryDetails # Assuming models.py is in app/

# Predefined lists (can be expanded and made more sophisticated)
INDICATOR_KEYWORDS = {
    "gdp": ["gdp", "gross domestic product"],
    "unemployment": ["unemployment rate", "unemployment", "jobless rate"],
    "inflation": ["inflation", "cpi", "consumer price index"],
    "housing": ["housing price", "hpi", "house price index", "home price index"],
    "population": ["population", "pop"],
    "interest rate": ["interest rate", "federal funds rate", "fed rate"],
    "nonfarm payrolls": ["nonfarm payrolls", "payrolls", "nfp"],
    # Add more common indicators
}

LOCATION_KEYWORDS = {
    "US": ["us", "usa", "united states", "national", "federal"],
    "CA": ["california", "ca"],
    "NY": ["new york", "ny"],
    "TX": ["texas", "tx"],
    "FL": ["florida", "fl"],
    # Add all state names and abbreviations from composite_tools.py state_codes
}
# Populate LOCATION_KEYWORDS with state_codes from composite_tools.py (or a shared source)
# This is just a placeholder for brevity in the subtask description.
# The actual implementation should have a comprehensive list.
_temp_state_codes = {
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
for name, code in _temp_state_codes.items():
    if code not in LOCATION_KEYWORDS: # Ensure code is a key
        LOCATION_KEYWORDS[code.upper()] = [name.lower()] # Use upper for code key consistency
    else:
        LOCATION_KEYWORDS[code.upper()].append(name.lower())
    
    # Add full name as a key too if not present, mapping to itself and its code
    # This helps in extraction if the full name is used as the canonical identifier internally
    lname = name.lower()
    if lname not in LOCATION_KEYWORDS: 
        LOCATION_KEYWORDS[lname] = [lname, code.lower()]
    else: # If already exists, ensure both name and code are in the list
        if lname not in LOCATION_KEYWORDS[lname]:
            LOCATION_KEYWORDS[lname].append(lname)
        if code.lower() not in LOCATION_KEYWORDS[lname]:
            LOCATION_KEYWORDS[lname].append(code.lower())


class QueryUnderstandingService:
    def __init__(self):
        # Can initialize more complex NLP models here if needed in the future
        pass

    def _extract_keywords(self, text_lower: str, keywords_map: Dict[str, List[str]]) -> List[str]:
        extracted = []
        for key, patterns in keywords_map.items():
            for pattern in patterns:
                # Use word boundaries for more precise matching of keywords
                # This helps avoid matching "us" in "housing" or "ca" in "calculate"
                # However, for multi-word patterns like "gross domestic product", simple substring is fine
                # For single short words like "us", "ca", "ny", boundaries are good.
                if len(pattern.split()) > 1: # multi-word pattern
                    if pattern in text_lower:
                        extracted.append(key)
                        break 
                else: # single-word pattern
                    if re.search(r"\b" + re.escape(pattern) + r"\b", text_lower):
                        extracted.append(key)
                        break 
        return list(set(extracted)) # Return unique keys

    def _extract_time_periods(self, text_lower: str) -> List[str]:
        periods = []
        # Regex for YYYY, YYYY-MM-DD, YYYY-MM
        # Simple year match - using word boundaries to avoid matching parts of other numbers
        year_match = re.findall(r'\b(19\d{2}|20\d{2})\b', text_lower)
        if year_match:
            periods.extend(year_match)

        # "last X years/months/days/quarters"
        last_x_match = re.findall(r'last (\d+) (year|month|day|quarter)s?', text_lower)
        if last_x_match:
            for num, unit in last_x_match:
                periods.append(f"last {num} {unit}s")
        
        if "latest" in text_lower or "current" in text_lower or "recent" in text_lower:
            periods.append("latest")
            
        # "from YYYY to YYYY" or "between YYYY and YYYY"
        range_match = re.findall(r'(?:from|between)\s+(19\d{2}|20\d{2})\s+(?:to|and)\s+(19\d{2}|20\d{2})', text_lower)
        if range_match:
            for start_year, end_year in range_match:
                 periods.append(f"{start_year} to {end_year}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_periods = []
        for x in periods:
            if x not in seen:
                unique_periods.append(x)
                seen.add(x)
        return unique_periods


    def _determine_query_type(self, raw_query_lower: str, indicators: List[str], locations: List[str], time_periods: List[str]) -> str:
        if any(kw in raw_query_lower for kw in ["compare", "vs", "versus", "against", "vs."]):
            # Check for comparison between locations for the same indicator(s)
            if len(locations) > 1 and len(indicators) >= 1:
                return "geographical_comparison" 
            # Check for comparison between indicators for the same location(s)
            elif len(indicators) > 1 and (len(locations) >= 1 or not locations): # Allow national comparison if no location
                return "indicator_comparison" 
             # Check for comparison over time for the same indicator and location
            elif len(time_periods) > 1 and len(indicators) >= 1 and (len(locations) >= 1 or not locations):
                return "time_comparison"
            else:
                return "comparison_generic" # Needs more info or entities to compare

        if any(kw in raw_query_lower for kw in ["trend", "history", "historical", "over time", "plot data for", "show me data for"]):
            return "trend_over_time"

        if any(kw in raw_query_lower for kw in ["search for", "find series", "look up", "what series match"]):
            return "series_search"
            
        if indicators and (locations or "US" in indicators): # If we have at least one indicator and location (or national indicator)
            # Keywords that strongly suggest asking for a specific value rather than a trend
            value_keywords = ["what is the", "get the current", "show me the value", "current value of", "latest value for"]
            if any(kw in raw_query_lower for kw in value_keywords) or ("latest" in time_periods and len(time_periods) == 1):
                return "single_datapoint" 
            return "data_retrieval" 
        
        # If it's just a term like "GDP" or "California" it might be an implicit search or underspecified retrieval
        if (indicators or locations) and not any(kw in raw_query_lower for kw in ["compare", "vs", "trend", "history", "search for"]):
            return "data_retrieval" # Or potentially "series_search" if very vague

        return "unknown"


    def parse_query(self, raw_query: str) -> QueryDetails:
        raw_query_lower = raw_query.lower()

        indicators = self._extract_keywords(raw_query_lower, INDICATOR_KEYWORDS)
        # Normalize location keys to upper case (e.g. 'CA') for consistency if they were extracted using full names
        extracted_locations = self._extract_keywords(raw_query_lower, LOCATION_KEYWORDS)
        normalized_locations = []
        for loc_key in extracted_locations:
            if loc_key.upper() in _temp_state_codes.values(): # If it's a state code
                normalized_locations.append(loc_key.upper())
            elif loc_key.lower() in _temp_state_codes.keys(): # If it's a state name
                 normalized_locations.append(_temp_state_codes[loc_key.lower()])
            elif loc_key.upper() == "US": # Special case for US
                 normalized_locations.append("US")
            else: # If it's already a key from LOCATION_KEYWORDS like 'US' or 'CA' (from its own definition)
                normalized_locations.append(loc_key) # Assume it's already in the desired format
        
        locations = list(set(normalized_locations))


        time_periods = self._extract_time_periods(raw_query_lower)
        
        query_type = self._determine_query_type(raw_query_lower, indicators, locations, time_periods)
        
        # Default time to 'latest' if no other time period is specified and it's a data retrieval/single point type
        if not time_periods and query_type not in ["series_search", "unknown", "comparison_generic"]:
            time_periods.append("latest")


        # Refine query type or parameters based on initial parsing
        if query_type == "unknown":
            if "search for" in raw_query_lower or "find series" in raw_query_lower:
                query_type = "series_search"
            elif indicators or locations: # If we have some entities but type is still unknown
                query_type = "data_retrieval"
            # If truly nothing specific, could be a general search term
            elif not indicators and not locations and not time_periods and raw_query_lower.strip():
                 query_type = "series_search"


        visualization_request_type = None # This will store the chart type string
        if any(kw in raw_query_lower for kw in ["plot", "graph", "chart", "visualize", "draw", "show a graph of"]):
            if query_type == "geographical_comparison" or query_type == "indicator_comparison":
                visualization_request_type = "comparison_bar_chart"
            elif query_type == "trend_over_time":
                visualization_request_type = "line_chart"
            elif query_type == "single_datapoint" and indicators and locations: # Make sure we have data to plot
                visualization_request_type = "snapshot_value_display"
            elif query_type == "data_retrieval" and indicators and (locations or "US" in indicators): # General data retrieval can be plotted
                visualization_request_type = "line_chart" # Default for data_retrieval
            else: 
                visualization_request_type = "generic_chart_request"


        parameters = {}
        if "normalize" in raw_query_lower or "normalized" in raw_query_lower:
            parameters["normalize"] = True
        

        return QueryDetails(
            raw_query=raw_query,
            query_type=query_type,
            indicators=indicators,
            locations=locations,
            time_periods=time_periods,
            parameters=parameters,
            visualization_request=visualization_request_type # Pass the determined chart type
        )

if __name__ == '__main__':
    # Test cases
    service = QueryUnderstandingService()
    queries = [
        "What is the latest GDP for US?",
        "Search for housing price index in California",
        "Plot the trend of unemployment rate for Texas over the last 5 years",
        "Compare GDP for California vs New York from 2020 to 2023, normalize the data",
        "Show me the historical population for USA",
        "US nonfarm payrolls",
        "Graph inflation for UK", # Location not in our simple list
        "GDP for CA",
        "Search for stuff",
        "interest rate US",
        "Compare US GDP and US unemployment rate", # Indicator comparison
        "Plot nonfarm payrolls for US and CA", # Geo comparison (implicit NFP for US vs NFP for CA)
        "search for oil prices",
        "what is the latest unemployment rate for Nevada",
        "unemployment rate for NV, CA, and AZ",
        "compare housing price index in texas vs florida last 2 years normalized",
        "draw a chart of the fed rate over the last 10 years"
    ]
    for q in queries:
        details = service.parse_query(q)
        print(f"Query: {q}")
        print(f"  Type: {details.query_type}")
        print(f"  Indicators: {details.indicators}")
        print(f"  Locations: {details.locations}")
        print(f"  Time Periods: {details.time_periods}")
        print(f"  Parameters: {details.parameters}")
        print(f"  Visualization: {details.visualization_request}")
        print("-" * 20)
