# DaLat TravelMate Agent — project guidance

## Goal and scope

Build an AI agent that recommends real places to eat, drink coffee, and visit in Da Lat from a user's Vietnamese natural-language preferences. Group recommendations by need. For each place, show an actual photo when available, name, Google rating and review count when available, address, a short evidence-based reason, and a clickable Google Maps link.

The MVP covers Da Lat only. Keep `location` explicit in data structures so another city can be supported later. Do not add daily itineraries, hotels, booking, or route optimization.

## Approved stack

Python, LangGraph, LangChain, DeepSeek API, SerpApi Google Maps, FastAPI, Streamlit, Docker, and Docker Compose. Do not introduce LangSmith, pytest, GitHub Actions, Kubernetes, Helm, MCP, or other infrastructure without a concrete need and user agreement.

## Working style

Build one small step at a time with the user. Explain each component, its input/output, and how it connects to the next component in clear Vietnamese. At the end of each step, run a meaningful manual check using sample inputs or real API data and explain the result. Do not implement the whole project at once.

The MVP ranking rule is implemented: favorable want/avoid evidence +1, unfavorable -1, mixed/unknown 0; break ties by Google rating, then preserve Search order. Consider every successfully assessed candidate. Any change to this rule should be discussed and validated with the user. Do not assume fixed weights, place counts, or API-call limits without a technical reason. Never invent place details or claim a preference is supported when the source data is missing or contradictory.

## Repository layout

Grow toward this layout as each step needs it; do not create placeholder files or directories merely to match the tree:

```text
app/                 Python package: config, schemas, graph, ranking, SerpApi and LLM clients, FastAPI
ui/                  Streamlit frontend that calls FastAPI
samples/             Example user requests and, later, sanitized SerpApi responses for repeatable manual checks
.env.example         Environment-variable names only; no secrets
.gitignore
requirements.txt
Dockerfile
compose.yaml
README.md
```

`samples/` is development/checking data, not the production source of recommended places. The running app should fetch place data through SerpApi. Keep API keys out of the repository.

## Implementation order

Start with project documentation/configuration and input/output schemas, then inspect live SerpApi responses for Da Lat. Next build and inspect the LangGraph flow, followed by evidence analysis and ranking. Add FastAPI, Streamlit, and Docker Compose after the agent works from Python. Verify optional API fields, photo URLs, review content, geographic relevance, and Google Maps links against real responses before relying on them.
