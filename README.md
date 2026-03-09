# Movies API - Python Demo

A Python Flask application for demonstrating Datadog's Continuous Profiler and error tracking.

## Features

- **Intentional performance issues** - O(n) lookups for profiling demos
- **Error-inducing endpoints** - Invalid regex patterns cause exceptions
- **MongoDB integration** - Credits data stored in MongoDB
- **Datadog integration** - APM, profiling, and error tracking

## Quick Start

### Option 1: Run Locally

```bash
# Start MongoDB
docker-compose up mongodb -d

# Install dependencies
cd python-app
pip install -r requirements.txt

# Copy movies data
cp ../movies-v2.json.gz .

# Run the server
export MOVIES_API_PORT=8080
export MONGO_URI=mongodb://localhost:27017
python server.py
```

### Option 2: Docker Compose (with Datadog)

```bash
# Set your Datadog API key
export DD_API_KEY=your-api-key

# Start everything
docker-compose up -d
```

## Load Testing

```bash
cd python-app

# Quick test
python test_endpoints.py

# Run forever with mixed good/bad queries (20% errors)
python test_endpoints.py --forever

# Custom error rate and speed
python test_endpoints.py --forever --error-rate 0.5 --rps 5
```

## API Endpoints

| Endpoint | Description | Notes |
|----------|-------------|-------|
| `GET /` | Random movie | Fast |
| `GET /movies?q=` | Search movies | Fast |
| `GET /credits?q=` | Movies with credits | ⚠️ Slow (O(n²)) |
| `GET /old-movies` | Movies before a year | Fast |
| `GET /stats?q=` | Crew statistics | ⚠️ Slow (O(n²)) |

## Performance Issues (Intentional)

The `/credits` and `/stats` endpoints use an inefficient O(n) lookup:

```python
def credits_for_movie(movie):
    # Scans ALL credits for each movie - SLOW!
    return [c for c in load_credits() if c.id == movie.id]
```

This is intentional for demonstrating how to identify hot spots with Datadog's Continuous Profiler.

## Error Scenarios

The test script sends invalid regex patterns that cause `re.error` exceptions:
- `[` → unterminated character set
- `*` → nothing to repeat
- `(` → missing closing paren

These appear in Datadog's Error Tracking.
