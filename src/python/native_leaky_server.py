"""
Native-memory-leaking Flask server for profiling demo.

Each request allocates memory via ctypes malloc() without ever freeing it.
RSS grows but Python heap (heap-live-size) stays flat, exercising
the RSS >> heap branch leading to PythonNativeLeakStep.
"""
import ctypes
import ctypes.util
import logging
import os

from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

app = Flask(__name__)
PORT = int(os.environ.get("MOVIES_API_PORT", "9088"))

libc_name = ctypes.util.find_library("c")
libc = ctypes.CDLL(libc_name)
libc.malloc.restype = ctypes.c_void_p
libc.malloc.argtypes = [ctypes.c_size_t]

NATIVE_ALLOCS: list = []
# 1 MiB per request → steep RSS growth, flat Python heap → clear RSS >> heap for auto-select
ALLOC_SIZE = 1024 * 1024  # 1 MiB per request


@app.route("/")
def index():
    # No gc.collect() - would increment gen2 count and wrongly trigger GC workflow
    ptr = libc.malloc(ALLOC_SIZE)
    if ptr:
        NATIVE_ALLOCS.append(ptr)
    return jsonify({
        "status": "native memory allocated",
        "alloc_count": len(NATIVE_ALLOCS),
        "total_native_mb": round(len(NATIVE_ALLOCS) * ALLOC_SIZE / (1024 * 1024), 2),
    })


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "alloc_count": len(NATIVE_ALLOCS),
    })


if __name__ == "__main__":
    LOG.info(
        "native-leaky-api-python starting on port %d (pid %d)",
        PORT, os.getpid(),
    )
    app.run(host="0.0.0.0", port=PORT)
