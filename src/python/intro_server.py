"""
Port of IntroServer.java.

Key characteristics (intentional for profiling demo):
- REQUEST_METRICS uses a dict keyed by request id (bounded by unique requests)
- credits_for_movie() does a linear O(n) scan of the full credits list
- No pre-computed CREDITS_BY_MOVIE_ID or MOVIES_WITH_CREDITS
- parse_role uses try/except (like Java valueOf try-catch)
"""
import logging
import os
import random
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import date

from flask import Flask, request, jsonify

from common import (
    Movie, Credit, CrewRole, MovieWithCredits, StatsResult,
    get_movies, get_credits,
)

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

MOVIES_API_PORT = int(os.environ.get("MOVIES_API_PORT", "8085"))

app = Flask(__name__)

# Metrics: dict keyed by request identity (bounded set, like Java HashMap<Request,Integer>)
REQUEST_METRICS: dict = {}
# CREDITS_BY_MOVIE_ID goes in here! (intentionally absent in intro server)


def collect_metrics(req) -> None:
    key = id(req)
    REQUEST_METRICS[key] = REQUEST_METRICS.get(key, 0) + 1


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


@app.route("/")
def random_movie_endpoint():
    collect_metrics(request)
    movies = get_movies()
    return jsonify(asdict(random.choice(movies)))


@app.route("/credits")
def credits_endpoint():
    query = request.args.get("q") or request.args.get("query")
    movies = get_movies()

    if query:
        p = re.compile(query, re.IGNORECASE)
        movies = [m for m in movies if m.title and p.search(m.title)]

    result = [MovieWithCredits(m, credits_for_movie(m)).to_dict() for m in movies]
    return jsonify(result)


@app.route("/movies")
def movies_endpoint():
    movies = sort_by_desc_release_date(get_movies())
    query = request.args.get("q") or request.args.get("query")
    if query:
        movies = [m for m in movies if m.title and query.upper() in m.title.upper()]
    return jsonify([asdict(m) for m in movies])


@app.route("/old-movies")
def old_movies_endpoint():
    year = request.args.get("year", "2010")
    limit = int(request.args.get("n", "10"))

    old_movies = [m for m in get_movies() if is_older_than(year, m)]
    LOG.debug("Found the following oldMovies: %s", old_movies)
    limited = old_movies[:limit]
    LOG.debug("With limit %d, the result was: %s", limit, limited)
    return jsonify([asdict(m) for m in limited])


@app.route("/stats")
def stats_endpoint():
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
    import os as _os
    LOG.info("Running version %s with pid %d", version.lower(), _os.getpid())

    # Warm up data at startup
    get_movies()
    get_credits()

    app.run(host="0.0.0.0", port=MOVIES_API_PORT)
