#!/usr/bin/env python3
"""
Find all .pprof files in the current directory and decode them using zstd.
Decoded files are prefixed with "decoded_".
"""

import os
import subprocess
import sys
from pathlib import Path


def decode_pprof_files(directory: str = "."):
    """Find and decode all pprof files in the given directory."""
    path = Path(directory)
    pprof_files = list(path.glob("*.pprof"))

    if not pprof_files:
        print("No .pprof files found in current directory")
        return

    print(f"Found {len(pprof_files)} pprof file(s)\n")

    success_count = 0

    for pprof_file in pprof_files:
        # Skip already decoded files
        if pprof_file.name.startswith("decoded_"):
            print(f"Skipping (already decoded): {pprof_file.name}")
            continue

        # Create decoded filename with prefix
        decoded_file = pprof_file.parent / f"decoded_{pprof_file.name}"

        print(f"Decoding: {pprof_file.name} -> {decoded_file.name}")

        try:
            # Run zstd to decompress
            result = subprocess.run(
                ["zstd", "-d", str(pprof_file), "-o", str(decoded_file), "-f"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"  ✅ Success")
                success_count += 1
            else:
                print(f"  ❌ Failed: {result.stderr.strip()}")

        except FileNotFoundError:
            print("  ❌ Error: zstd not found. Install with: brew install zstd")
            sys.exit(1)
        except Exception as e:
            print(f"  ❌ Error: {e}")

    print(f"\nDecoded {success_count}/{len(pprof_files)} pprof file(s)")


if __name__ == "__main__":
    # Use current directory or first argument
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    decode_pprof_files(directory)
