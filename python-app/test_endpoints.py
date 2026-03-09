#!/usr/bin/env python3
"""
Continuous load generator for Movies API endpoints.

Mixes good queries with bad ones that cause exceptions.

Usage:
    python test_endpoints.py              # Run quick tests
    python test_endpoints.py --load       # Run continuous load (mixed good/bad)
    python test_endpoints.py --slow       # Hit the slow endpoints
"""

import argparse
import json
import random
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError

BASE_URL = "http://localhost:8080"

# ============================================================================
# GOOD QUERIES - These work fine
# ============================================================================
GOOD_QUERIES = [
    "the", "jurassic", "matrix", "star", "love",
    "war", "night", "dark", "man", "world",
    "action", "comedy", "drama", "horror", "sci-fi",
]

# ============================================================================
# BAD QUERIES - These cause exceptions!
# ============================================================================
BAD_QUERIES = [
    # Invalid regex patterns - cause re.error
    "[",           # Unclosed character class
    "(",           # Unclosed group
    "*",           # Nothing to repeat
    "?",           # Nothing to repeat
    "+",           # Nothing to repeat
    "\\",          # Trailing backslash
    "[a-",         # Incomplete range
    "(foo",        # Unclosed paren
    "(?P<>foo)",   # Invalid group name

    # Edge cases that might cause issues
    "",            # Empty query
    " " * 1000,    # Very long whitespace
    "a" * 10000,   # Very long query (regex timeout?)
]

# Backwards compat
QUERIES = GOOD_QUERIES


def make_request(endpoint: str, params: dict = None) -> dict:
    """Make a GET request and return JSON response."""
    url = f"{BASE_URL}{endpoint}"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query_string}"

    try:
        with urlopen(url, timeout=10) as response:
            return {
                "status": response.status,
                "data": json.loads(response.read().decode()),
                "url": url
            }
    except URLError as e:
        return {"status": "error", "error": str(e), "url": url}
    except TimeoutError:
        return {"status": "timeout", "error": "Request timed out", "url": url}
    except Exception as e:
        return {"status": "error", "error": str(e), "url": url}


def test_random_movie():
    """Test GET / endpoint."""
    print("\n🎬 Testing GET / (random movie)...")
    result = make_request("/")
    if result.get("status") == 200:
        movie = result["data"]
        print(f"   ✅ Got: {movie.get('title', 'Unknown')}")
    else:
        print(f"   ❌ Error: {result}")
    return result


def test_movies(query: str = None):
    """Test GET /movies endpoint."""
    print(f"\n🎬 Testing GET /movies{'?q=' + query if query else ''}...")
    params = {"q": query} if query else None
    result = make_request("/movies", params)
    if result.get("status") == 200:
        count = len(result["data"])
        print(f"   ✅ Got {count} movies")
    else:
        print(f"   ❌ Error: {result}")
    return result


def test_credits(query: str = None):
    """Test GET /credits endpoint (SLOW!)."""
    print(f"\n🐌 Testing GET /credits{'?q=' + query if query else ''} (this is SLOW)...")
    start = time.time()
    params = {"q": query} if query else None
    result = make_request("/credits", params)
    elapsed = time.time() - start
    if result.get("status") == 200:
        count = len(result["data"])
        print(f"   ✅ Got {count} movies with credits in {elapsed:.2f}s")
    else:
        print(f"   ❌ Error: {result}")
    return result


def test_old_movies(year: str = "2000", limit: int = 5):
    """Test GET /old-movies endpoint."""
    print(f"\n🎬 Testing GET /old-movies?year={year}&n={limit}...")
    result = make_request("/old-movies", {"year": year, "n": limit})
    if result.get("status") == 200:
        count = len(result["data"])
        print(f"   ✅ Got {count} old movies")
    else:
        print(f"   ❌ Error: {result}")
    return result


def test_stats(query: str = None):
    """Test GET /stats endpoint (SLOW!)."""
    print(f"\n🐌 Testing GET /stats{'?q=' + query if query else ''} (this is SLOW)...")
    start = time.time()
    params = {"q": query} if query else None
    result = make_request("/stats", params)
    elapsed = time.time() - start
    if result.get("status") == 200:
        data = result["data"]
        print(f"   ✅ Matched {data.get('matchedMovies', 0)} movies in {elapsed:.2f}s")
        print(f"   📊 Crew counts: {data.get('crewCount', {})}")
    else:
        print(f"   ❌ Error: {result}")
    return result


def run_quick_tests():
    """Run a quick test of all endpoints."""
    print("=" * 60)
    print("🚀 Running quick endpoint tests")
    print("=" * 60)

    test_random_movie()
    test_movies("jurassic")
    test_old_movies("2000", 3)
    test_credits("jurassic")  # Small query = faster
    test_stats("jurassic")    # Small query = faster

    print("\n" + "=" * 60)
    print("✅ Quick tests complete!")
    print("=" * 60)


def run_slow_tests():
    """Run the slow endpoints with broad queries."""
    print("=" * 60)
    print("🐌 Running SLOW endpoint tests (broad queries)")
    print("=" * 60)

    test_credits("the")  # Matches many movies = SLOW
    test_stats("the")    # Matches many movies = SLOW

    print("\n" + "=" * 60)
    print("✅ Slow tests complete!")
    print("=" * 60)


def run_load_test(duration_seconds: int = 60, requests_per_second: float = 2, error_rate: float = 0.2):
    """
    Run continuous load against all endpoints.

    Mixes good queries (~80%) with bad queries (~20%) that cause exceptions.
    """
    print("=" * 60)
    print("🔥 Running MIXED load test")
    print(f"   Duration: {duration_seconds}s at ~{requests_per_second} req/s")
    print(f"   Error rate: {error_rate*100:.0f}% bad queries (cause exceptions)")
    print("   Press Ctrl+C to stop")
    print("=" * 60)

    start_time = time.time()
    request_count = 0
    success_count = 0
    error_count = 0

    endpoints = ["/", "/movies", "/old-movies", "/credits", "/stats"]

    try:
        while time.time() - start_time < duration_seconds:
            endpoint = random.choice(endpoints)

            # Decide if this should be a good or bad request
            use_bad_query = random.random() < error_rate

            if endpoint == "/":
                params = None
            elif endpoint == "/old-movies":
                params = {"year": "2010", "n": "10"}
            else:
                # Use good or bad query
                if use_bad_query:
                    query = random.choice(BAD_QUERIES)
                else:
                    query = random.choice(GOOD_QUERIES)
                params = {"q": query}

            result = make_request(endpoint, params)
            request_count += 1

            status = result.get("status")
            if status == 200:
                success_count += 1
            else:
                error_count += 1

            # Print each request (verbose mode)
            if request_count <= 20 or request_count % 50 == 0:
                q = params.get("q", "-")[:20] if params else "-"
                status_icon = "✅" if status == 200 else "💥"
                print(f"   {status_icon} {endpoint:15} q={q:20} -> {status}")
            elif request_count == 21:
                print("   ... (showing every 50th request now)")

            # Rate limiting
            time.sleep(1 / requests_per_second)

    except KeyboardInterrupt:
        print("\n   ⏹ Stopped by user")

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    print(f"   Total requests:  {request_count}")
    print(f"   Successful (2xx): {success_count} ({100*success_count/max(request_count,1):.1f}%)")
    print(f"   Errors (5xx):    {error_count} ({100*error_count/max(request_count,1):.1f}%)")
    print(f"   Duration:        {elapsed:.1f}s")
    print(f"   Throughput:      {request_count/elapsed:.1f} req/s")


def check_server():
    """Check if the server is running."""
    try:
        with urlopen(f"{BASE_URL}/", timeout=30):
            return True
    except (URLError, OSError):
        return False


def run_forever(requests_per_second: float = 1, error_rate: float = 0.2):
    """Run load indefinitely until Ctrl+C."""
    print("=" * 60)
    print(f"🔄 Running FOREVER at ~{requests_per_second} req/s")
    print(f"   Error rate: {error_rate*100:.0f}% bad queries")
    print("   Press Ctrl+C to stop")
    print("=" * 60)

    request_count = 0
    success_count = 0
    error_count = 0
    start_time = time.time()

    endpoints = ["/", "/movies", "/old-movies", "/credits", "/stats"]

    try:
        while True:
            endpoint = random.choice(endpoints)
            use_bad_query = random.random() < error_rate

            if endpoint == "/":
                params = None
            elif endpoint == "/old-movies":
                params = {"year": "2010", "n": "10"}
            else:
                query = random.choice(BAD_QUERIES if use_bad_query else GOOD_QUERIES)
                params = {"q": query}

            result = make_request(endpoint, params)
            request_count += 1

            if result.get("status") == 200:
                success_count += 1
            else:
                error_count += 1

            # Progress every 100 requests
            if request_count % 100 == 0:
                elapsed = time.time() - start_time
                print(f"   📈 {request_count} total | ✅ {success_count} ok | 💥 {error_count} errors | {request_count/elapsed:.1f} req/s")

            time.sleep(1 / requests_per_second)

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n⏹ Stopped after {request_count} requests in {elapsed:.1f}s")
        print(f"   ✅ Success: {success_count} | 💥 Errors: {error_count}")


def main():
    parser = argparse.ArgumentParser(description="Test the Movies API endpoints")
    parser.add_argument("--load", action="store_true", help="Run timed load test (default 60s)")
    parser.add_argument("--forever", action="store_true", help="Run load indefinitely until Ctrl+C")
    parser.add_argument("--slow", action="store_true", help="Run slow endpoint tests")
    parser.add_argument("--duration", type=int, default=60, help="Load test duration in seconds")
    parser.add_argument("--rps", type=float, default=2, help="Requests per second")
    parser.add_argument("--error-rate", type=float, default=0.2, help="Fraction of bad queries (0.0-1.0)")
    parser.add_argument("--url", type=str, default="http://localhost:8080", help="Base URL")

    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url

    print(f"🎯 Target: {BASE_URL}")

    if not check_server():
        print(f"❌ Server not responding at {BASE_URL}")
        print("   Make sure the server is running: python server.py")
        sys.exit(1)

    print("✅ Server is up!")

    if args.forever:
        run_forever(args.rps, args.error_rate)
    elif args.load:
        run_load_test(args.duration, args.rps, args.error_rate)
    elif args.slow:
        run_slow_tests()
    else:
        run_quick_tests()


if __name__ == "__main__":
    main()
