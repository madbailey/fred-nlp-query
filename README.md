# fred-nlp-query

This repository is being reworked from an older Streamlit/LangChain prototype into a typed FRED analysis system with deterministic data execution, chart generation, and an LLM only where ambiguity actually exists.

The working rebuild plan lives at `docs/rework-plan.md`.

Current state:

- The checked-in app is an abandoned prototype and should not be treated as the target architecture.
- The next implementation pass should focus on the core engine first: query intent, series resolution, FRED retrieval, transforms, and chart specs.
- UI work should stay thin until the engine is correct and testable.

Current implementation:

- `src/fred_query/` contains the new typed backend package.
- The first deterministic flow is implemented for state real GDP comparison.
- `tests/` covers transforms, the direct FRED client, and the California-vs-Texas comparison path.

Verification:

- Run tests with `PYTHONPATH=src python -m unittest discover -s tests -v`

Run the current backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
fred-query compare-state-gdp --state1 California --state2 Texas --start-date 2019-01-01
```

Without installing the package:

```powershell
$env:PYTHONPATH="src"
python -m fred_query compare-state-gdp --state1 California --state2 Texas --start-date 2019-01-01 --format json
```

Natural-language parser:

```powershell
fred-query ask "How has California's GDP compared with Texas since 2019?"
fred-query ask "Show me the unemployment rate since 2020" --format json
```

`ask` requires a working OpenAI API key and quota. If parser calls fail, the command exits with a hard error instead of falling back.
