"""Stream a large fintech media file through an Infrai multipart upload."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from infrai_storage import Infrai


DEFAULT_PART_SIZE = 8 * 1024 * 1024


def _operation_id(bucket: str, key: str, source: Path) -> str:
    stat = source.stat()
    material = f"{bucket}\0{key}\0{stat.st_size}\0{stat.st_mtime_ns}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def put_part(url: str, chunk: bytes, *, max_attempts: int = 5) -> str:
    for attempt in range(max_attempts):
        request = Request(url, data=chunk, method="PUT")
        try:
            with urlopen(request) as response:
                etag = response.headers.get("ETag")
                if not etag:
                    raise RuntimeError("part response did not include an ETag")
                return etag
        except HTTPError as exc:
            if exc.code != 429 or attempt + 1 == max_attempts:
                raise
            delay = float(exc.headers.get("Retry-After") or 2**attempt)
            time.sleep(delay)
    raise RuntimeError("part retry budget exhausted")


def upload_media(
    source: Path,
    bucket: str,
    key: str,
    infrai: Infrai,
    *,
    upload_chunk: Callable[[str, bytes], str] = put_part,
) -> dict[str, Any]:
    operation_id = _operation_id(bucket, key, source)
    infrai.storage.bucket.create(
        name=bucket,
        bucket=bucket,
        idempotency_key=f"bucket:{bucket}",
    )

    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    created = infrai.storage.multipart.create(
        bucket,
        key=key,
        content_type=content_type,
        idempotency_key=f"{operation_id}:create",
    )
    upload_id = str(created["upload_id"])
    part_size = max(int(created.get("part_size_min", DEFAULT_PART_SIZE)), DEFAULT_PART_SIZE)

    parts: list[dict[str, Any]] = []
    with source.open("rb") as stream:
        part_number = 1
        while chunk := stream.read(part_size):
            signed = infrai.storage.multipart.presign_part(upload_id, part_number)
            etag = upload_chunk(str(signed["url"]), chunk)
            parts.append({"part_number": part_number, "etag": etag})
            part_number += 1

    return infrai.storage.multipart.complete(
        upload_id,
        parts=parts,
        idempotency_key=f"{operation_id}:complete",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a large fintech media file")
    parser.add_argument("source", type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()

    result = upload_media(args.source, args.bucket, args.key, Infrai.from_env())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
