# FRED Data Finder

A Streamlit application that allows users to query economic data from the Federal Reserve Economic Data (FRED) database using natural language. The application uses Google's Gemini 1.5 Pro to interpret questions and provide visualizations and analyses of economic data.

![App Screenshot](https://via.placeholder.com/800x450)

## Features

- **Natural Language Queries**: Ask questions about economic data in plain English
- **Data Visualization**: Automatic generation of charts and graphs for better understanding
- **Economic Analysis**: Comparison of data across states, time periods, and indicators
- **User-Friendly Interface**: Simple chat interface for seamless interaction

## Query Examples

- "What's the current unemployment rate in Texas?"
- "Show me housing prices in California with a chart"
- "Compare GDP between California and Texas"
- "How does GDP in 2023 compare to before the pandemic in 2019?"
- "What's the trend in housing prices over the last decade?"
- "Show me how Florida's unemployment rate compares to the national average"

## Installation

### Using Docker (Recommended)

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/fred-data-finder.git
   cd fred-data-finder
   ```

2. Create a `.env` file with your API keys:
   ```
   FRED_API_KEY=your_fred_api_key
   GOOGLE_API_KEY=your_google_api_key
   ```

3. Build and run the Docker container:
   ```
   docker-compose up --build
   ```

4. Access the application at http://localhost:8501

### Manual Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/fred-data-finder.git
   cd fred-data-finder
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your API keys:
   ```
   FRED_API_KEY=your_fred_api_key
   GOOGLE_API_KEY=your_google_api_key
   ```

4. Run the Streamlit application:
   ```
   streamlit run app/main.py
   ```

## Getting API Keys

### FRED API Key
1. Visit the [FRED API Key Request Page](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Register for an account and request an API key
3. Add the key to your `.env` file

### Google API Key
1. Visit the [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key with access to the Gemini models
3. Add the key to your `.env` file

## Project Structure

- `app/main.py`: Main Streamlit application
- `app/prompts.py`: System prompts for the LLM
- `app/utils/tools.py`: Basic FRED API tools
- `app/utils/composite_tools.py`: Advanced analysis tools
- `app/utils/enhanced_tools.py`: User-friendly specialized tools
- `.streamlit/config.toml`: Streamlit configuration

## Technical Details

- **Streamlit**: Web application framework
- **LangChain**: Structured tools and agent framework
- **FRED API**: Economic data source
- **Google Gemini 1.5 Pro**: Large language model for query interpretation
- **Matplotlib**: Data visualization
- **Docker**: Containerization for easy deployment

## Rate Limiting

The application includes rate limiting to prevent exceeding API quotas:
- Maximum of 10 API calls per minute
- Automatic backoff when rate limits are reached

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Federal Reserve Bank of St. Louis](https://fred.stlouisfed.org/) for providing the FRED API
- [Streamlit](https://streamlit.io/) for the web application framework
- [LangChain](https://langchain.com/) for the agent framework
- [Google Gemini](https://deepmind.google/technologies/gemini/) for the language model