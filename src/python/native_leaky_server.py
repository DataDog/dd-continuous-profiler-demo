"""
Native-memory-leaking Flask server for profiling demo.

Each request allocates native memory via ctypes malloc(). Python heap stays
flat (no Python objects retained), while RSS grows steadily — RSS >> Live Heap
triggers the "No, RSS is much higher than heap" path in the decision tree.
"""
import ctypes
import ctypes.util
import gc
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
# 2 MiB native per request; RSS grows ~2 MiB/s, Python Live Heap stays flat
ALLOC_SIZE = 2 * 1024 * 1024  # 2 MiB per request
LEAK_ENABLED = os.environ.get("LEAK_ENABLED", "1") == "1"


@app.route("/")
def index():
    # Reset gen2 count to 0 on every request so runtime.python.gc.count.gen2
    # stays flat — prevents the startup artifact (count grows 0→10 before first
    # auto gen2 trigger) from falsely routing to the GC pressure step.
    gc.collect(2)
    if LEAK_ENABLED:
        ptr = libc.malloc(ALLOC_SIZE)
        if ptr:
            libc.memset(ptr, 0, ALLOC_SIZE)  # touch pages so RSS grows (malloc is lazy)
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
