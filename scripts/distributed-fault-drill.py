#!/usr/bin/python3

"""Exercise interrupted transfer resume, corruption rejection, and final checksum."""

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compresso.libs.resumable_transfer import ResumableTransferStore, file_sha256  # noqa: E402


def checksum(data):
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-mb", type=int, default=100)
    parser.add_argument("--chunk-mb", type=int, default=8)
    args = parser.parse_args()
    total_size = max(1, args.size_mb) * 1024 * 1024
    chunk_size = max(1, args.chunk_mb) * 1024 * 1024

    with tempfile.TemporaryDirectory(prefix="compresso-fault-drill-") as root:
        source_path = os.path.join(root, "source.bin")
        with open(source_path, "wb") as output:
            remaining = total_size
            while remaining:
                block = os.urandom(min(chunk_size, remaining))
                output.write(block)
                remaining -= len(block)
        expected = file_sha256(source_path)
        store_root = os.path.join(root, "transfers")
        store = ResumableTransferStore(store_root)
        status = store.begin("fault-drill", "source.bin", total_size, expected)
        transfer_id = status["transfer_id"]

        with open(source_path, "rb") as source:
            offset = 0
            chunk_number = 0
            while offset < total_size:
                source.seek(offset)
                data = source.read(chunk_size)
                if chunk_number == 1:
                    try:
                        store.append(transfer_id, offset, data, checksum(b"corrupt"))
                    except ValueError:
                        pass
                    else:
                        raise RuntimeError("corrupt chunk was accepted")
                store.append(transfer_id, offset, data, checksum(data))
                offset += len(data)
                chunk_number += 1
                store = ResumableTransferStore(store_root)
                if store.status(transfer_id)["offset"] != offset:
                    raise RuntimeError("resume offset was not durable")

        completed = store.finalize(transfer_id)
        if file_sha256(completed) != expected:
            raise RuntimeError("final checksum mismatch")
        print(f"PASS: resumed {chunk_number} chunks and verified {total_size} bytes")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
