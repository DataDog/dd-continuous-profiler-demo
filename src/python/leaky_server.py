"""
Port of LeakyServer.java.

Key characteristics (intentional for profiling demo):
- REQUEST_METRICS is an unbounded list (never cleared)
- Each Metrics object holds a large metadata string (256 KiB) in Python heap
- This produces a memory leak observable in Datadog Python Live Heap and profiler
- credits_for_movie() does a linear O(n) scan (no pre-computed map)
- parse_role uses try/except
"""
import logging
import os
import random
import re
import threading
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime

from flask import Flask, request, jsonify

from common import (
    Movie, CrewRole, MovieWithCredits, StatsResult,
    get_movies, get_credits,
)

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

MOVIES_API_PORT = int(os.environ.get("MOVIES_API_PORT", "8082"))

app = Flask(__name__)


# Bytes of Python heap to leak per request. Pure Python strings show up in
# Python Live Heap (heap-live-size). 16 KiB × 2 req/s = 32 KiB/s → ~5h OOM cycle at 512 Mi,
# giving reliable detection in any 15-min window (28 MiB growth per window >> 8% threshold).
_LEAK_BYTES_PER_REQUEST = 16 * 1024


class Metrics:
    """Intentional memory leak using Python heap objects.

    Uses a large string (and dicts/lists) that allocate through pymalloc so
    the leak is visible in Datadog's Python Live Heap metric and heap profiler.
    """

    def __init__(self, req):
        self.req_method = req.method
        self.req_url = req.url
        self.req_args = str(req.args)
        self.req_headers = str(dict(req.headers))
        self.date = datetime.utcnow()
        # Large string: pure Python heap, drives steep slope in Python Live Heap
        self.metadata = "x" * _LEAK_BYTES_PER_REQUEST
        self.data = [
            {"key": f"val_{i}", "nested": list(range(100))}
            for i in range(50)
        ]


# Unbounded list - the leak (mirrors Java LinkedList<Metrics>)
REQUEST_METRICS: list = []
_metrics_lock = threading.Lock()

# CREDITS_BY_MOVIE_ID goes in here! (intentionally absent in leaky server)

_credits_cache_ready = False
_MOVIES_WITH_CREDITS: list = []


def _ensure_cache():
    global _MOVIES_WITH_CREDITS, _credits_cache_ready
    if _credits_cache_ready:
        return
    _MOVIES_WITH_CREDITS = [
        MovieWithCredits(m, credits_for_movie(m)) for m in get_movies()
    ]
    _credits_cache_ready = True


def collect_metrics(req) -> None:
    """Synchronized append - mirrors Java synchronized collectMetrics."""
    with _metrics_lock:
        REQUEST_METRICS.append(Metrics(req))


def credits_for_movie(movie: Movie) -> list:
    """O(n) linear scan - intentional for profiling demo."""
    return [c for c in get_credits() if c.id == movie.id]


def crew_count_for_movie(credits: list) -> dict:
    if not credits:
        return {}
    credit = credits[0]
    counts: dict = defaultdict(int)
    for role_str in credit.crew_role:
        role = CrewRole.parse_role_try_except(role_str)
        counts[role.value] += 1
    return dict(counts)


def sort_by_desc_release_date(movies: list) -> list:
    def key(m: Movie):
        try:
            return date.fromisoformat(m.releaseDate)
        except Exception:
            return date.min
    return sorted(movies, key=key, reverse=True)


def is_older_than(year: str, movie: Movie) -> bool:
    result = (movie.releaseDate or "") < year
    LOG.debug("Is %s older than %s? %s", movie, year, result)
    return result


@app.route("/spawn-thread")
def spawn_thread_endpoint():
    """Spawns a daemon thread that sleeps forever, causing thread count to grow."""
    collect_metrics(request)
    t = threading.Thread(target=lambda: time.sleep(86400), daemon=True)
    t.start()
    return jsonify({"status": "thread spawned", "count": threading.active_count()})


@app.route("/")
def random_movie_endpoint():
    collect_metrics(request)
    movies = get_movies()
    return jsonify(asdict(random.choice(movies)))


@app.route("/credits")
def credits_endpoint():
    collect_metrics(request)
    _ensure_cache()
    query = request.args.get("q") or request.args.get("query")
    movies_with_credits = _MOVIES_WITH_CREDITS

    if query:
        p = re.compile(query, re.IGNORECASE)
        movies_with_credits = [
            mwc for mwc in movies_with_credits
            if mwc.movie.title and p.search(mwc.movie.title)
        ]

    return jsonify([mwc.to_dict() for mwc in movies_with_credits])


@app.route("/movies")
def movies_endpoint():
    collect_metrics(request)
    movies = sort_by_desc_release_date(get_movies())
    query = request.args.get("q") or request.args.get("query")
    if query:
        movies = [m for m in movies if m.title and query.upper() in m.title.upper()]
    return jsonify([asdict(m) for m in movies])


@app.route("/old-movies")
def old_movies_endpoint():
    collect_metrics(request)
    year = request.args.get("year", "2010")
    limit = int(request.args.get("n", "10"))

    old_movies = [m for m in get_movies() if is_older_than(year, m)]
    LOG.debug("Found the following oldMovies: %s", old_movies)
    limited = old_movies[:limit]
    LOG.debug("With limit %d, the result was: %s", limit, limited)
    return jsonify([asdict(m) for m in limited])


@app.route("/stats")
def stats_endpoint():
    collect_metrics(request)
    query = request.args.get("q") or request.args.get("query")
    movies = get_movies()

    if query:
        p = re.compile(query, re.IGNORECASE)
        movies = [m for m in movies if m.title and p.search(m.title)]

    number_matched = len(movies)
    aggregated: dict = defaultdict(int)
    for movie in movies:
        for role, count in crew_count_for_movie(credits_for_movie(movie)).items():
            aggregated[role] += count

    return jsonify(StatsResult(number_matched, dict(aggregated)).to_dict())


if __name__ == "__main__":
    version = os.environ.get("DD_VERSION", "(not set)")
    LOG.info("Running version %s with pid %d", version.lower(), os.getpid())

    # Warm up data at startup (cache builds lazily on first /credits request)
    get_movies()
    get_credits()

    app.run(host="0.0.0.0", port=MOVIES_API_PORT)
