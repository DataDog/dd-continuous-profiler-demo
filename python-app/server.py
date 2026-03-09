"""
Movies API Server - Python Port
Demonstrates performance issues for Datadog Continuous Profiler workshop.

This is an intentionally inefficient implementation (like IntroServer.java)
that performs O(n) lookups instead of using a map-based approach.
"""

import gzip
import json
import os
import random
import re
from datetime import datetime
from functools import lru_cache
from typing import Optional

from flask import Flask, jsonify, request
from pymongo import MongoClient

app = Flask(__name__)

# Configuration
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MOVIES_API_PORT = int(os.environ.get("MOVIES_API_PORT", "8080"))

# In-memory request metrics (similar to Java version)
REQUEST_METRICS: dict = {}


# =============================================================================
# Data Loading
# =============================================================================

@lru_cache(maxsize=1)
def load_movies() -> list[dict]:
    """Load movies from gzipped JSON file."""
    movies_file = os.path.join(os.path.dirname(__file__), "..", "movies-v2.json.gz")

    # Fallback to current directory if not found
    if not os.path.exists(movies_file):
        movies_file = "movies-v2.json.gz"

    try:
        with gzip.open(movies_file, "rt", encoding="utf-8") as f:
            movies = json.load(f)
            app.logger.info(f"Loaded {len(movies)} movies from {movies_file}")
            return movies
    except FileNotFoundError:
        app.logger.warning(f"Movies file not found: {movies_file}, using sample data")
        return [
            {"id": "1", "title": "Jurassic Park", "originalTitle": "Jurassic Park",
             "releaseDate": "1993-06-11", "overview": "Dinosaurs!", "tagline": "Life finds a way", "voteAverage": "8.1"},
            {"id": "2", "title": "The Matrix", "originalTitle": "The Matrix",
             "releaseDate": "1999-03-31", "overview": "Red pill or blue pill?", "tagline": "Reality is wrong", "voteAverage": "8.7"},
            {"id": "3", "title": "Inception", "originalTitle": "Inception",
             "releaseDate": "2010-07-16", "overview": "Dreams within dreams", "tagline": "Your mind is the scene of the crime", "voteAverage": "8.4"},
        ]


@lru_cache(maxsize=1)
def load_credits() -> list[dict]:
    """Load credits from MongoDB."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client["moviesDB"]
        credits_collection = db["credits"]
        credits = list(credits_collection.find({}, {"_id": 0}))
        app.logger.info(f"Loaded {len(credits)} credits from MongoDB")
        client.close()
        return credits
    except Exception as e:
        app.logger.warning(f"Failed to load credits from MongoDB: {e}, using sample data")
        return [
            {"id": "1", "crew": ["Steven Spielberg (Director)", "Michael Crichton (Writer)"], "cast": ["Sam Neill", "Laura Dern"]},
            {"id": "2", "crew": ["Lana Wachowski (Director)", "Lilly Wachowski (Writer)"], "cast": ["Keanu Reeves", "Laurence Fishburne"]},
            {"id": "3", "crew": ["Christopher Nolan (Director)", "Christopher Nolan (Screenplay)"], "cast": ["Leonardo DiCaprio", "Tom Hardy"]},
        ]


# =============================================================================
# Optimized O(1) Credit Lookup
# =============================================================================

@lru_cache(maxsize=1)
def load_credits_by_id() -> dict[str, dict]:
    """Build O(1) lookup dict from credits."""
    credits_by_id = {}
    for c in load_credits():
        credits_by_id[c.get("id")] = c
    return credits_by_id


def credits_for_movie(movie: dict) -> list[dict]:
    """
    O(1) lookup using pre-built dict.

    Previously this was O(n) - scanning all credits for each movie.
    Now it's O(1) - direct dict lookup.
    """
    movie_id = movie.get("id")
    credit = load_credits_by_id().get(movie_id)
    return [credit] if credit else []


def parse_crew_role(crew_member: str) -> str:
    """Extract role from 'Name (Role)' format."""
    match = re.search(r"\((.+)\)", crew_member)
    if match:
        role = match.group(1)
        if role in ("Director", "Writer", "Screenplay", "Editor", "Animation"):
            return role
    return "Other"


def crew_count_for_movie(credits: list[dict]) -> dict[str, int]:
    """Count crew members by role."""
    if not credits:
        return {}

    credit = credits[0]
    crew = credit.get("crew", [])

    counts: dict[str, int] = {}
    for member in crew:
        role = parse_crew_role(member)
        counts[role] = counts.get(role, 0) + 1

    return counts


# =============================================================================
# Metrics Collection (similar to Java version)
# =============================================================================

def collect_metrics(req):
    """Track request metrics."""
    key = f"{req.method}:{req.path}"
    REQUEST_METRICS[key] = REQUEST_METRICS.get(key, 0) + 1


# =============================================================================
# Sorting Helper
# =============================================================================

def sort_by_desc_release_date(movies: list[dict]) -> list[dict]:
    """Sort movies by release date, descending."""
    def parse_date(m):
        try:
            return datetime.strptime(m.get("releaseDate", ""), "%Y-%m-%d")
        except ValueError:
            return datetime.min

    return sorted(movies, key=parse_date, reverse=True)


# =============================================================================
# API Endpoints
# =============================================================================

@app.route("/")
def random_movie():
    """Return a random movie."""
    collect_metrics(request)
    movies = load_movies()
    movie = random.choice(movies)
    return jsonify(movie)


@app.route("/movies")
def movies_endpoint():
    """List movies, optionally filtered by query."""
    collect_metrics(request)
    movies = load_movies()
    movies = sort_by_desc_release_date(movies)

    query = request.args.get("q") or request.args.get("query")
    if query:
        pattern = re.compile(query, re.IGNORECASE)
        movies = [m for m in movies if m.get("title") and pattern.search(m["title"])]

    return jsonify(movies)


@app.route("/credits")
def credits_endpoint():
    """
    Return movies with their credits.

    WARNING: This endpoint is SLOW due to O(n) lookups in credits_for_movie().
    This is intentional for demonstrating profiling.
    """
    collect_metrics(request)
    movies = load_movies()

    query = request.args.get("q") or request.args.get("query")
    if query:
        pattern = re.compile(query, re.IGNORECASE)
        movies = [m for m in movies if m.get("title") and pattern.search(m["title"])]

    # This is where the O(n^2) performance issue manifests
    # For each movie, we scan ALL credits to find matching ones
    movies_with_credits = [
        {"movie": movie, "credits": credits_for_movie(movie)}
        for movie in movies
    ]

    return jsonify(movies_with_credits)


@app.route("/old-movies")
def old_movies_endpoint():
    """Return movies older than a given year."""
    collect_metrics(request)

    year = request.args.get("year", "2010")
    limit = int(request.args.get("n", "10"))

    movies = load_movies()
    old_movies = [m for m in movies if m.get("releaseDate", "9999") < year]
    limited = old_movies[:limit]

    app.logger.debug(f"Found {len(old_movies)} old movies, returning {len(limited)}")
    return jsonify(limited)


@app.route("/stats")
def stats_endpoint():
    """
    Return aggregated crew statistics.

    WARNING: This endpoint is SLOW due to O(n) lookups for each movie.
    """
    collect_metrics(request)
    movies = load_movies()

    query = request.args.get("q") or request.args.get("query")
    if query:
        pattern = re.compile(query, re.IGNORECASE)
        movies = [m for m in movies if m.get("title") and pattern.search(m["title"])]

    # Aggregate crew counts - O(n^2) due to credits_for_movie()
    aggregated_stats: dict[str, int] = {}
    for movie in movies:
        credits = credits_for_movie(movie)  # O(n) lookup!
        counts = crew_count_for_movie(credits)
        for role, count in counts.items():
            aggregated_stats[role] = aggregated_stats.get(role, 0) + count

    return jsonify({
        "matchedMovies": len(movies),
        "crewCount": aggregated_stats
    })


# =============================================================================
# Error Handler
# =============================================================================

@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler."""
    app.logger.error(f"Unhandled exception: {e}", exc_info=True)
    return jsonify({"error": str(e)}), 500


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    # Warm up caches
    app.logger.info("Warming up caches...")
    load_movies()
    load_credits()
    load_credits_by_id()  # Build the O(1) lookup dict

    app.logger.info(f"Starting Movies API on port {MOVIES_API_PORT} (threaded)")
    app.run(host="0.0.0.0", port=MOVIES_API_PORT, debug=False, threaded=True)
