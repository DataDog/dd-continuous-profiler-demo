import gzip
import json
import os
import re
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

# Path to movie data - env override takes precedence (used in Docker),
# otherwise fall back to repo root relative to this file
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.join(_HERE, "..", "..")
MOVIES_GZ_PATH = os.environ.get(
    "MOVIES_GZ_PATH",
    os.path.join(_REPO_ROOT, "movies-v2.json.gz"),
)


@dataclass
class Movie:
    id: str
    originalTitle: Optional[str]
    overview: Optional[str]
    releaseDate: str
    tagline: Optional[str]
    title: Optional[str]
    voteAverage: Optional[str]

    def __repr__(self):
        return json.dumps(asdict(self))


@dataclass
class Credit:
    id: str
    crew: list
    cast: list
    crew_role: list  # transient - extracted from crew strings

    @staticmethod
    def _get_role(name_and_role: str) -> str:
        m = re.search(r"\((.*)\)", name_and_role)
        return m.group(1) if m else "Other"

    @classmethod
    def from_document(cls, doc) -> "Credit":
        crew = doc.get("crew") or []
        cast = doc.get("cast") or []
        crew_role = [cls._get_role(c) for c in crew]
        return cls(id=doc["id"], crew=crew, cast=cast, crew_role=crew_role)

    def to_dict(self):
        return {"id": self.id, "crew": self.crew, "cast": self.cast}


@dataclass
class MovieWithCredits:
    movie: Movie
    credits: list  # List[Credit]

    def to_dict(self):
        return {
            "movie": asdict(self.movie),
            "credits": [c.to_dict() for c in (self.credits or [])],
        }


@dataclass
class StatsResult:
    matchedMovies: int
    crewCount: dict

    def to_dict(self):
        return {"matchedMovies": self.matchedMovies, "crewCount": self.crewCount}


class CrewRole(str, Enum):
    Director = "Director"
    Writer = "Writer"
    Screenplay = "Screenplay"
    Editor = "Editor"
    Animation = "Animation"
    Other = "Other"

    @classmethod
    def parse_role_try_except(cls, input_role: str) -> "CrewRole":
        """Used by IntroServer, Server, LeakyServer (mirrors Java try-catch)."""
        try:
            return cls(input_role)
        except ValueError:
            return cls.Other

    @classmethod
    def parse_role_dict(cls, input_role: str) -> "CrewRole":
        """Used by TimelineServer (mirrors Java ROLES_MAP.getOrDefault)."""
        _ROLES_MAP = {r.value: r for r in cls}
        return _ROLES_MAP.get(input_role, cls.Other)


# --- Cached data loading ---

_movies_cache = None
_credits_cache = None


def get_movies() -> list:
    global _movies_cache
    if _movies_cache is None:
        _movies_cache = _load_movies()
    return _movies_cache


def get_credits() -> list:
    global _credits_cache
    if _credits_cache is None:
        _credits_cache = _load_credits()
    return _credits_cache


def _load_movies() -> list:
    with gzip.open(MOVIES_GZ_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)
    movies = []
    for d in data:
        movies.append(Movie(
            id=d.get("id", ""),
            originalTitle=d.get("originalTitle"),
            overview=d.get("overview"),
            releaseDate=d.get("releaseDate", ""),
            tagline=d.get("tagline"),
            title=d.get("title"),
            voteAverage=d.get("voteAverage"),
        ))
    return movies


def _load_credits() -> list:
    client = MongoClient(MONGO_URI)
    try:
        collection = client["moviesDB"]["credits"]
        return [Credit.from_document(doc) for doc in collection.find().batch_size(5000)]
    finally:
        client.close()
