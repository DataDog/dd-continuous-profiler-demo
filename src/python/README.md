# Python Port

Python/Flask port of the Java Continuous Profiler demo services. Runs alongside the Java services using the same MongoDB instance and Datadog agent.

## Prerequisites

- Docker and docker-compose
- A Datadog API key

## Services

| Service | Port | Java equivalent |
|---|---|---|
| `intro-movies-api-python` | 9085 | `intro-movies-api-java` (8085) |
| `movies-api-python` | 9081 | `movies-api-java` (8081) |
| `leaky-api-python` | 9082 | `leaky-api-java` (8082) |
| `movies-api-python-timeline` | 9083 | `movies-api-java-timeline` (8083) |

## Starting the demo

### All services (Java + Python)

```bash
export DD_API_KEY=<your-api-key>
docker-compose up
```

### Python services only

```bash
export DD_API_KEY=<your-api-key>
docker-compose up movies-api-mongo datadog-agent \
  intro-movies-api-python \
  movies-api-python \
  leaky-api-python \
  movies-api-python-timeline \
  loadgen-leak-python \
  loadgen-movies-api-python \
  loadgen-timeline-python \
  loadgen-movies-api-intro-python
```

### Single service with load tester

Each service has a paired load generator. To run just one service end-to-end, always include `movies-api-mongo` and `datadog-agent` as dependencies.

**Intro**
```bash
docker-compose up movies-api-mongo datadog-agent \
  intro-movies-api-python \
  loadgen-movies-api-intro-python
```

**Movies (optimised)**
```bash
docker-compose up movies-api-mongo datadog-agent \
  movies-api-python \
  loadgen-movies-api-python
```

**Both intro and optimized**
```bash
docker-compose up datadog-agent movies-api-mongo intro-movies-api-python loadgen-movies-api-intro-python movies-api-python loadgen-movies-api-python
```

**Leaky**
```bash
docker-compose up movies-api-mongo datadog-agent \
  leaky-api-python \
  loadgen-leak-python
```

**Timeline**
```bash
docker-compose up movies-api-mongo datadog-agent \
  movies-api-python-timeline \
  loadgen-timeline-python
```

## Verifying the services

Once running, test each endpoint:

```bash
curl http://localhost:9081/                        # random movie
curl http://localhost:9081/movies?q=jurassic       # search movies
curl http://localhost:9081/credits?q=the           # movies with cast/crew
curl http://localhost:9081/old-movies?year=2005    # movies older than year
curl http://localhost:9081/stats?q=the             # crew role stats
```

Replace `9081` with `9082`, `9083`, or `9085` to hit the other services.

## What each service demonstrates

- **intro** (`9085`) — baseline: O(n) credits lookup, bounded metrics dict
- **movies** (`9081`) — optimised: O(1) credits lookup via pre-computed dict
- **leaky** (`9082`) — intentional memory leak: every request appends a `Metrics` object containing 1MB of data to an unbounded list, visible in the Datadog heap profiler
- **timeline** (`9083`) — same as movies, but `parse_role` uses a dict lookup instead of try/except — the incremental optimisation the timeline view highlights
