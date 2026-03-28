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
    # Force gen1 collections so runtime.python.gc.count.gen2 grows steadily.
    # gc.collect(1) increments gc.get_count()[2]; gc.collect(2) resets it to 0.
    # 10×/req at 5 req/s = 50 gen1/sec → count[2] ramps clearly over 15 min.
    for _ in range(10):
        gc.collect(1)
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
    # Raise the gen2 threshold so automatic gen2 collections never fire.
    # gc.collect(1) in the handler increments gc.get_count()[2]; without this,
    # the counter resets to 0 every 10 gen1 collections (default threshold).
    # With a huge threshold it grows monotonically: 50/s × 900s = 45 000 in 15 min.
    gc.set_threshold(700, 10, 10_000_000)
    # threaded=False keeps thread count flat so Step 2 (thread leak) doesn't trigger
    app.run(host="0.0.0.0", port=PORT, threaded=False)
