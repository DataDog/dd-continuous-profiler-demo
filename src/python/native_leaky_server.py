"""
Native-memory-leaking Flask server for profiling demo.

Each request allocates native memory via ctypes malloc() and a small Python
heap allocation. Heap grows slowly; RSS grows faster (native dominates).
Detector may need both: heap growth + RSS >> heap for "No, RSS Is Much Higher".
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
libc.memset.restype = ctypes.c_void_p
libc.memset.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]

NATIVE_ALLOCS: list = []
HEAP_METADATA: list = []  # small Python leak so heap grows slowly
# 2 MiB native + 64 KiB Python per request; heap ~64 KiB/s, RSS ~2 MiB/s
ALLOC_SIZE = 2 * 1024 * 1024  # 2 MiB per request
HEAP_CHUNK = 64 * 1024  # 64 KiB Python metadata per request


@app.route("/")
def index():
    # No gc.collect() - would increment gen2 count and wrongly trigger GC workflow
    ptr = libc.malloc(ALLOC_SIZE)
    if ptr:
        libc.memset(ptr, 0, ALLOC_SIZE)  # touch pages so RSS grows (malloc is lazy)
        NATIVE_ALLOCS.append(ptr)
    # Small Python heap leak so Live Heap grows slowly; detector may need this
    HEAP_METADATA.append("x" * HEAP_CHUNK)
    return jsonify({
        "status": "native memory allocated",
        "alloc_count": len(NATIVE_ALLOCS),
        "total_native_mb": round(len(NATIVE_ALLOCS) * ALLOC_SIZE / (1024 * 1024), 2),
        "heap_chunks": len(HEAP_METADATA),
    })


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "alloc_count": len(NATIVE_ALLOCS),
        "heap_chunks": len(HEAP_METADATA),
    })


if __name__ == "__main__":
    LOG.info(
        "native-leaky-api-python starting on port %d (pid %d)",
        PORT, os.getpid(),
    )
    app.run(host="0.0.0.0", port=PORT)
