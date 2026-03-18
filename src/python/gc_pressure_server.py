"""
GC-pressure Flask server for profiling demo.

Each request forces many gen2 collections via gc.collect(2).
runtime.python.gc.count.gen2 grows steadily. No survivor pool growth so
the pod does not OOM and reset the cumulative counter.
"""
import gc
import logging
import os

from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

app = Flask(__name__)
PORT = int(os.environ.get("MOVIES_API_PORT", "9087"))


@app.route("/")
def index():
    # Force many gen2 collections so runtime.python.gc.count.gen2 grows steeply.
    # No survivor pool growth — OOM resets the counter and breaks the trend.
    # 500×/req at 5 req/s = 2500 gen2/sec; memory stays flat.
    for _ in range(500):
        gc.collect(2)
    gen2 = gc.get_stats()[2]["collections"]
    return jsonify({
        "status": "gc pressure applied",
        "gen2_collections": gen2,
    })


@app.route("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    LOG.info(
        "gc-pressure-api-python starting on port %d (pid %d)",
        PORT, os.getpid(),
    )
    # threaded=False keeps thread count flat so Step 2 (thread leak) doesn't trigger
    app.run(host="0.0.0.0", port=PORT, threaded=False)
