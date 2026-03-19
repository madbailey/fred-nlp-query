# FRED NLP Query
 <img width="900" height="476" alt="image" src="https://github.com/user-attachments/assets/aabaf2d7-ee42-4087-a9fe-b3478e67c464" />

A natural language interface for retrieving data from  Federal Reserve Economic Data (FRED). Ask questions about economic indicators in plain English and get structured data and visualizations back.
 
## What It Does
 
FRED NLP Query lets users interact with the FRED database conversationally. Instead of manually looking up series codes and constructing API requests, you can ask something like:
 
```
"Show me the unemployment rate since 2020"
"How has California's GDP compared with Texas since 2019?"
```
 <img width="800" height="735" alt="image" src="https://github.com/user-attachments/assets/3f9a6ac5-b6cc-423d-9c51-98685566d852" />

The application parses your intent using an LLM, maps it to the correct FRED series and parameters, executes the query deterministically against the FRED API, and returns structured data — all through a REST API, browser UI, or CLI.
The LLM is used *only* for intent parsing and clarification. All data retrieval and execution is deterministic.
 
## Architecture
 
```
┌──────────────┐     ┌──────────────────┐     ┌────────────┐
│  Browser UI  │────▶│   FastAPI App     │────▶│  FRED API  │
│  or CLI      │◀────│                   │◀────│            │
└──────────────┘     │  ┌─────────────┐  │     └────────────┘
                     │  │ LLM (OpenAI)│  │
                     │  │ Intent only │  │
                     │  └─────────────┘  │
                     └──────────────────┘
```
 
- **API Layer** — FastAPI handles request validation, routing, and structured JSON error responses
- **NLP Layer** — OpenAI integration parses natural language into typed query parameters
- **Data Layer** — Typed query engine executes against the FRED API with Pydantic models
- **Presentation** — Browser UI served as static assets from the same FastAPI app, plus a CLI
 
## Tech Stack
 
| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Web Framework | FastAPI |
| HTTP Client | httpx |
| LLM Integration | OpenAI API |
| Validation | Pydantic v2 |
| Server | Uvicorn |
| Frontend | Vanilla JavaScript, CSS, HTML |
| Containerization | Docker + Docker Compose |
| Packaging | setuptools with pyproject.toml |


 ### Prerequisites
 
- Python 3.12+
- A [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) (free)
- An [OpenAI API key](https://platform.openai.com/api-keys) (required for natural language queries)

### Local Development
 
```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .\.venv\Scripts\Activate.ps1   # Windows PowerShell
 
pip install -U pip
pip install -e .
```
 
### Run the App
 
```bash
uvicorn fred_query.api.app:app --reload
```
 
Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).
 
### Run with Docker
 
```bash
docker compose up --build
```
 

 
