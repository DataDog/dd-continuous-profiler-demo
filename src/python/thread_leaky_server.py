"""
Thread-leaking Flask server for profiling demo.

Each request spawns a daemon thread that sleeps forever.
runtime.python.thread_count grows linearly, exercising
the "Yes" branch of PythonResourceCheckStep.
"""
import logging
import os
import threading
import time

from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

app = Flask(__name__)
PORT = int(os.environ.get("MOVIES_API_PORT", "9086"))
LEAK_ENABLED = os.environ.get("LEAK_ENABLED", "1") == "1"


@app.route("/")
def index():
    if LEAK_ENABLED:
        t = threading.Thread(target=lambda: time.sleep(86400), daemon=True)
        t.start()
    return jsonify({
        "status": "thread spawned",
        "active_threads": threading.active_count(),
    })


@app.route("/health")
def health():
    return jsonify({"ok": True, "threads": threading.active_count()})


if __name__ == "__main__":
    LOG.info(
        "thread-leaky-api-python starting on port %d (pid %d)",
        PORT, os.getpid(),
    )
    app.run(host="0.0.0.0", port=PORT)
