# fred-nlp-query

Typed FRED query engine with a FastAPI backend, a thin browser UI, deterministic data execution, and an LLM only for intent parsing and clarification.

## Supported Surface

- `src/fred_query/` is the supported application package.
- FastAPI serves the API and browser UI from the same app.
- The browser UI is packaged with the Python distribution and served from `/`.

## API Endpoints

- `GET /health`
- `POST /api/ask`
- `POST /api/compare/state-gdp`
- `GET /`

Request validation now happens at the API boundary. Handled failures return structured JSON error payloads instead of plain-text 500 responses.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
```

## Run The App

```powershell
uvicorn fred_query.api.app:app --reload
```

Then open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Run Tests

After `pip install -e .`:

```powershell
python -m unittest discover -s tests -v
```

Without installing the package:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

## Example API Calls

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/ask -ContentType "application/json" -Body '{"query":"Show me the unemployment rate since 2020"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/compare/state-gdp -ContentType "application/json" -Body '{"state1":"California","state2":"Texas","start_date":"2019-01-01","normalize":true}'
```

## CLI

```powershell
fred-query compare-state-gdp --state1 California --state2 Texas --start-date 2019-01-01
fred-query ask "How has California's GDP compared with Texas since 2019?"
fred-query ask "Show me the unemployment rate since 2020" --format json
```

`ask` requires a working OpenAI API key and quota. FRED-backed execution requires a FRED API key.

## Container

```powershell
docker compose up --build
```
