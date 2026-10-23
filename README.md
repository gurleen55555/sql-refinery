# SQL-Refinery

**AI-assisted SQL optimization with correctness verification and performance benchmarking.**

Built for the **NVIDIA × Nebius Global AI Hackathon**, SQL-Refinery uses NVIDIA Nemotron through Nebius Token Factory to propose SQL rewrites, then independently validates and benchmarks them against a controlled local DuckDB demo database.

> **Core principle:** AI proposes. The application validates. Measurements decide whether a rewrite is faster.

## ✨ What It Does

- **AI-assisted rewrites:** Ask Nemotron for an alternative SQL query.
- **SQL safety checks:** Parse and validate candidate queries before execution.
- **Correctness verification:** Compare the original and candidate query results before treating the rewrite as equivalent.
- **Performance benchmarking:** Use warm-up runs, repeated measurements, and median timings to compare execution time.
- **Local demo database:** Run against a predefined DuckDB dataset.
- **Automated tests:** Test core validation and benchmarking behavior without spending API credits.

## 🏗️ Architecture

The application separates AI suggestions from SQL validation, execution, correctness checks, and performance measurement. The model does **not** get to declare its own output safe or correct.

```mermaid
flowchart TB
    subgraph UI["1 · Presentation Layer"]
        A["User enters SQL"]
        B["Streamlit UI<br/>app/main.py"]
        A --> B
    end

    subgraph AI["2 · AI Suggestion Layer"]
        C["NVIDIA Nemotron"]
        D["Nebius Token Factory API"]
        E["Candidate SQL rewrite"]
        C <--> D
        D --> E
    end

    subgraph VERIFY["3 · Validation & Execution Layer"]
        F["SQLGlot parsing"]
        G{"Allowed read-only<br/>query?"}
        H["Execute original and candidate"]
        I["Compare result sets"]
        J{"Results equivalent?"}
        R["Reject candidate"]
        F --> G
        G -- No --> R
        G -- Yes --> H
        H --> I
        I --> J
        J -- No --> R
    end

    subgraph DB["4 · Data Layer"]
        K[("DuckDB demo database")]
    end

    subgraph PERF["5 · Benchmarking Layer"]
        L["Warm-up runs"]
        M["Repeated timed runs"]
        N["Median execution time"]
        O["Compare measured performance"]
        L --> M --> N --> O
    end

    B -- "Request rewrite" --> C
    E -- "Suggested SQL" --> B
    B -- "Original and candidate SQL" --> F
    H <--> K
    J -- Yes --> L
    O --> B
    R --> B

    classDef ui fill:#e8f2ff,stroke:#4385d1,color:#17365d
    classDef ai fill:#e6f7ed,stroke:#38a169,color:#14532d
    classDef verify fill:#f0eaff,stroke:#805ad5,color:#44337a
    classDef data fill:#e0f5fa,stroke:#319795,color:#234e52
    classDef perf fill:#fff4db,stroke:#dd8b00,color:#744210
    classDef reject fill:#ffe5e5,stroke:#dc2626,color:#991b1b

    class A,B ui
    class C,D,E ai
    class F,G,H,I,J verify
    class K data
    class L,M,N,O perf
    class R reject
```

### Request Lifecycle

1. The user submits a SQL query through the Streamlit interface.
2. Nemotron generates a proposed rewrite through Nebius Token Factory.
3. The application parses and validates the candidate against its supported read-only SQL rules.
4. The original and candidate queries execute against the controlled DuckDB demo database.
5. Their results are compared. A candidate that fails validation or equivalence checks must not be treated as a verified rewrite.
6. Only an accepted, equivalent candidate proceeds to performance benchmarking.
7. The application reports measured performance instead of assuming that every rewrite is faster.

### Code Map

| File | Responsibility |
|---|---|
| `app/main.py` | Streamlit interface and application workflow |
| `app/llm.py` | Calls Nemotron through the Nebius-compatible API |
| `app/sql_runner.py` | SQL parsing, safety validation, query execution, and result comparison |
| `app/benchmark.py` | Warm-up runs, repeated timing, and benchmark summaries |
| `app/config.py` | Reads application configuration and environment variables |
| `tests/` | Automated tests for core behavior |

## 🧰 Tech Stack

- **Language:** Python 3.10+
- **UI:** Streamlit
- **AI Model:** NVIDIA Nemotron
- **Model API:** Nebius Token Factory
- **SQL Parsing:** SQLGlot
- **Local Query Engine:** DuckDB
- **API Client:** OpenAI Python SDK
- **Testing:** pytest

## 🛡️ Safety & Correctness

SQL-Refinery is a local demo application, not a production SQL security boundary.

- Supports a restricted single-statement, read-only SQL workflow, including supported `SELECT` and `WITH` queries.
- Rejects unsupported or destructive statement types before execution.
- Validates candidate SQL independently of the LLM.
- Uses a predefined demo schema and dataset rather than arbitrary external database connections.
- Compares query results before treating a rewrite as equivalent.
- Treats model output as untrusted input.

SQL parsing and application-level checks are defense-in-depth. They are not a substitute for database permissions, sandboxing, resource limits, or a production security review.

## 📊 Benchmarking Approach

SQL-Refinery measures performance instead of promising that every AI-generated rewrite is an optimization.

- **Warm-up executions:** Reduce the impact of first-run effects.
- **Repeated measurements:** Observe execution time across multiple runs.
- **Median timings:** Reduce sensitivity to unusually fast or slow runs.
- **Performance comparison:** Compare original and candidate query execution times.
- **Honest reporting:** A rewrite may produce equivalent results without being faster.

Results depend on the query, dataset, hardware, and runtime conditions. Measurements from the local demo database are illustrative and do not guarantee production performance improvements.

## 🚀 Getting Started

### Requirements

- Python 3.10 or newer
- A Nebius Token Factory API key for AI rewrite requests

### 1. Clone the Repository

```powershell
git clone https://github.com/gurleen55555/sql-refinery.git
cd sql-refinery
```

If you already have the repository locally, navigate to its project folder instead.

### 2. Create and Activate a Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks environment activation, you can run the environment's Python executable directly using `.venv\Scripts\python.exe`.

### 3. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure the API

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and set `NEBIUS_API_KEY` to your own API key. Never commit your real API key to GitHub.

Check `.env.example` for the supported configuration variables and defaults.

The default API base URL is:

```text
https://api.tokenfactory.nebius.com/v1/
```

The model ID is configurable through `NEBIUS_MODEL`. Use a model identifier supported by your Nebius Token Factory account.

### 5. Start the Application

```powershell
python -m streamlit run app/main.py
```

Streamlit will display a local URL in the terminal. Open that URL in your browser to use SQL-Refinery.

## 🧪 Run Tests

Run the test suite with:

```powershell
python -m pytest
```

The automated tests are designed to verify core behavior without making model API calls, helping conserve API credits.

## 🔐 Environment & Secrets

- Store credentials in your local `.env` file.
- Keep `.env` out of version control.
- Use `.env.example` to document required configuration variables without including real secrets.
- Never expose your Nebius API key in source code, screenshots, logs, or public repositories.
- Rotate the key immediately if it is accidentally exposed.

## 🗺️ Project Status

SQL-Refinery is an evolving hackathon project demonstrating a careful workflow for AI-assisted SQL rewriting.

Its central idea is simple: **an AI-generated query is only a useful optimization candidate when it passes independent validation, produces equivalent results, and is evaluated using actual performance measurements.**

## 📄 License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for details.