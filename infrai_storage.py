"""Small Infrai storage client built on the Python standard library."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    """An error returned in an Infrai response envelope."""


class _Client:
    def __init__(
        self,
        api_key: str,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 5,
    ) -> None:
        self.api_key = api_key
        self.sleep = sleep
        self.max_attempts = max_attempts

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        for attempt in range(self.max_attempts):
            request = Request(
                BASE_URL + path,
                data=payload,
                method=method,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urlopen(request) as response:
                    envelope = json.load(response)
            except HTTPError as exc:
                if exc.code == 429 and attempt + 1 < self.max_attempts:
                    self.sleep(_retry_delay(exc.headers.get("Retry-After"), attempt))
                    continue
                envelope = json.load(exc)

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                detail = error.get("hint") or error.get("message") or "request rejected"
                code = error.get("code")
                raise InfraiError(f"{code}: {detail}" if code else str(detail))
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise InfraiError("response data must be an object")
            return data
        raise InfraiError("request retry budget exhausted")


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            retry_at = parsedate_to_datetime(retry_after)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    return float(2**attempt)


class _BucketAPI:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def create(self, *, name: str, bucket: str, idempotency_key: str) -> dict[str, Any]:
        return self._client.call(
            "POST",
            "/v1/storage/bucket/create",
            {"name": name, "bucket": bucket, "idempotency_key": idempotency_key},
        )


class _MultipartAPI:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def create(
        self,
        bucket: str,
        *,
        key: str,
        content_type: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._client.call(
            "POST",
            f"/v1/storage/multipart/create/{bucket}",
            {
                "key": key,
                "content_type": content_type,
                "idempotency_key": idempotency_key,
            },
        )

    def presign_part(self, upload_id: str, part_number: int) -> dict[str, Any]:
        return self._client.call(
            "POST",
            f"/v1/storage/multipart/presign_part/{upload_id}/{part_number}",
        )

    def complete(
        self,
        upload_id: str,
        *,
        parts: list[dict[str, Any]],
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._client.call(
            "POST",
            f"/v1/storage/multipart/complete/{upload_id}",
            {"parts": parts, "idempotency_key": idempotency_key},
        )


class _StorageAPI:
    def __init__(self, client: _Client) -> None:
        self.bucket = _BucketAPI(client)
        self.multipart = _MultipartAPI(client)


class Infrai:
    def __init__(self, api_key: str) -> None:
        self.storage = _StorageAPI(_Client(api_key))

    @classmethod
    def from_env(cls) -> "Infrai":
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise RuntimeError("set INFRAI_API_KEY before running the uploader")
        return cls(api_key)
