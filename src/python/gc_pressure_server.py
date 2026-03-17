"""
GC-pressure Flask server for profiling demo.

Each request creates objects with circular references stored in a global list.
Objects survive to gen2 garbage collection, causing
runtime.python.gc.count.gen2 to grow steadily.
"""
import gc
import logging
import os

from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

app = Flask(__name__)
PORT = int(os.environ.get("MOVIES_API_PORT", "9087"))

SURVIVOR_POOL: list = []


class CyclicNode:
    """Object with a circular reference that forces GC collection."""

    __slots__ = ("peer", "payload")

    def __init__(self):
        self.peer = None
        # ~2 KB payload; 20 groups × 2 nodes × 2 KB ≈ 80 KB/req → ~15 min OOM at 256 Mi, 3.5 req/s
        self.payload = list(range(70))


def create_cyclic_group():
    """Create a pair of objects that reference each other."""
    a = CyclicNode()
    b = CyclicNode()
    a.peer = b
    b.peer = a
    return a


@app.route("/")
def index():
    for _ in range(20):
        SURVIVOR_POOL.append(create_cyclic_group())
    # Force gen2 collection so runtime.python.gc.count.gen2 grows steadily
    # (natural gen2 runs ~every 70k allocations; explicit collect makes it visible)
    gc.collect(2)
    gen2 = gc.get_stats()[2]["collections"]
    return jsonify({
        "status": "gc pressure applied",
        "survivor_count": len(SURVIVOR_POOL),
        "gen2_collections": gen2,
    })


@app.route("/health")
def health():
    return jsonify({"ok": True, "survivors": len(SURVIVOR_POOL)})


if __name__ == "__main__":
    LOG.info(
        "gc-pressure-api-python starting on port %d (pid %d)",
        PORT, os.getpid(),
    )
    app.run(host="0.0.0.0", port=PORT)
