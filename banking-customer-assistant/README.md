# Banking Customer Chat Assistant POC

Python-first proof of concept: Streamlit UI → FastAPI backend → LangGraph orchestration → deterministic risk policy → agents (account/card/loan/RAG/dispute/complaint) → mock banking API / SQLite / RabbitMQ events.

## Prerequisites

- Python 3.11+ (a `.venv` is already set up in this repo)
- A [Groq](https://console.groq.com/) API key (optional — the assistant falls back to deterministic keyword matching and raw retrieved text if omitted)
- Docker, only if you want to run a real RabbitMQ broker (optional — see below)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `GROQ_API_KEY` if you have one. Everything else has a safe demo default.

Build the FAISS index for policy Q&A (only needed once, and again whenever `knowledge_base/*.md` changes):

```bash
python -m rag.ingest
```

## Running

Start the backend and the UI in two terminals:

```bash
uvicorn backend.main:app --reload --port 8000
streamlit run app.py
```

Streamlit talks to FastAPI over HTTP (`API_BASE_URL`, default `http://localhost:8000`) — it does not import backend modules directly.

### Optional: real RabbitMQ

By default (`RABBITMQ_ENABLED=false`), dispute/card/complaint events are audited and "sent" (mock email + mock SMS) synchronously in-process — no broker needed. To see real message-queue behavior:

```bash
docker-compose up rabbitmq
```

Then set `RABBITMQ_ENABLED=true` in `.env`, restart the backend, and run the consumer in a third terminal:

```bash
python -m events.consumer_runner
```

## Running tests

```bash
pytest
```

## Demo credentials

| Customer ID | PIN  | Name         |
|---|---|---|
| CUST001 | 1234 | Rahul Sharma |
| CUST002 | 2345 | Priya Singh  |
| CUST003 | 3456 | Amit Kumar   |

Login generates a random 6-digit OTP shown directly in the demo UI (expires in 5 minutes, 3 attempts allowed, a new login invalidates the previous OTP). Email is mocked to a single `DEMO_EMAIL` address for all customers; SMS is always mocked — there is no real SMS/OTP provider integration.
