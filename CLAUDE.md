# Fred NLP Query Project Settings

## Build & Run Commands
- Run app locally: `streamlit run app/main.py`
- Docker build: `docker build -t fred-nlp-query .`
- Docker run: `docker run -p 8501:8501 --env-file .env fred-nlp-query`
- Docker compose: `docker-compose up --build`

## Code Style Guidelines
- **Imports**: Use absolute imports organized in groups (standard library, 3rd party, local)
- **Typing**: Use Python type hints with Pydantic models for validated inputs
- **Error Handling**: Use try/except blocks with detailed error messages
- **Naming**: Use snake_case for variables/functions, CamelCase for classes
- **Logging**: Use standard Python logging module configured with logging.basicConfig
- **Docstrings**: Use descriptive docstrings for all functions and classes

## Architecture Notes
- Streamlit frontend with LangChain backend for LLM integration
- FRED API wrapper for economic data access
- Tools are organized as basic tools (tools.py) and composite tools (composite_tools.py)
- Use normalized visualization (base=100) when comparing different scales