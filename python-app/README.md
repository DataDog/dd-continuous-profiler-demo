# Movies API - Python Port

Python port of the Datadog Continuous Profiler demo application.

## Features

This is an **intentionally inefficient** implementation that mirrors `IntroServer.java`. It demonstrates performance issues that can be identified using Datadog's Continuous Profiler:

- **O(n) credit lookups**: The `credits_for_movie()` function scans all credits for each movie instead of using a dictionary lookup
- **O(n²) endpoints**: `/credits` and `/stats` endpoints exhibit quadratic time complexity

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MONGO_URI=mongodb://localhost:27017
export MOVIES_API_PORT=8080

# Copy movies data
cp ../movies-v2.json.gz .

# Run the server
python server.py
```

### With Docker

```bash
# Build
docker build -t movies-api-python .

# Run
docker run -p 8080:8080 \
  -e MONGO_URI=mongodb://host.docker.internal:27017 \
  movies-api-python
```

### With Datadog Profiling

```bash
# Set your Datadog API key
export DD_API_KEY=your-api-key

# Run with ddtrace
DD_PROFILING_ENABLED=true \
DD_SERVICE=movies-api-python \
DD_ENV=prod \
ddtrace-run python server.py
```

## API Endpoints

| Endpoint | Description | Query Params |
|----------|-------------|--------------|
| `GET /` | Random movie | - |
| `GET /movies` | List movies (sorted by date) | `q` - filter by title |
| `GET /credits` | Movies with cast/crew ⚠️ SLOW | `q` - filter by title |
| `GET /old-movies` | Movies before a year | `year`, `n` |
| `GET /stats` | Crew role statistics ⚠️ SLOW | `q` - filter by title |

## Performance Issue

The intentional performance bottleneck is in `credits_for_movie()`:

```python
def credits_for_movie(movie: dict) -> list[dict]:
    # O(n) scan - SLOW!
    return [c for c in load_credits() if c.get("id") == movie_id]
```

The fix would be to use a dictionary:

```python
@lru_cache(maxsize=1)
def credits_by_movie_id() -> dict[str, list[dict]]:
    credits = load_credits()
    result = {}
    for c in credits:
        movie_id = c.get("id")
        if movie_id not in result:
            result[movie_id] = []
        result[movie_id].append(c)
    return result

def credits_for_movie(movie: dict) -> list[dict]:
    # O(1) lookup - FAST!
    return credits_by_movie_id().get(movie.get("id"), [])
```

## Testing

```bash
# Get a random movie
curl http://localhost:8080/

# Search movies
curl "http://localhost:8080/movies?q=jurassic"

# Get credits (slow!)
curl "http://localhost:8080/credits?q=jurassic"

# Get stats (slow!)
curl "http://localhost:8080/stats?q=the"
```
