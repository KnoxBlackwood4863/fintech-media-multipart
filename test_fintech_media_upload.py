from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from fintech_media_upload import upload_media


class FakeBucket:
    def __init__(self, events: list[tuple]) -> None:
        self.events = events

    def create(self, **body):
        self.events.append(("bucket", body))
        return {"bucket": body["bucket"]}


class FakeMultipart:
    def __init__(self, events: list[tuple]) -> None:
        self.events = events

    def create(self, bucket, **body):
        self.events.append(("create", bucket, body))
        return {"upload_id": "upload-42", "part_size_min": 1}

    def presign_part(self, upload_id, part_number):
        self.events.append(("presign", upload_id, part_number))
        return {"url": f"https://uploads.example/part/{part_number}"}

    def complete(self, upload_id, **body):
        self.events.append(("complete", upload_id, body))
        return {"key": "evidence/interview.wav", "size_bytes": 9}


class MultipartUploadTest(TestCase):
    def test_creates_bucket_uploads_parts_and_completes(self) -> None:
        events: list[tuple] = []
        storage = SimpleNamespace(
            bucket=FakeBucket(events),
            multipart=FakeMultipart(events),
        )
        client = SimpleNamespace(storage=storage)

        with TemporaryDirectory() as directory:
            source = Path(directory) / "interview.wav"
            source.write_bytes(b"audit-log")
            result = upload_media(
                source,
                "fintech-media",
                "evidence/interview.wav",
                client,
                upload_chunk=lambda url, chunk: f'etag-{len(chunk)}',
            )

        self.assertEqual(events[0][0], "bucket")
        self.assertEqual(events[1][0], "create")
        self.assertEqual(events[-1][0], "complete")
        self.assertEqual(events[-1][2]["parts"], [{"part_number": 1, "etag": "etag-9"}])
        self.assertEqual(result["size_bytes"], 9)
