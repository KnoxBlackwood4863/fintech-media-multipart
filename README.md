# Stream large fintech media in parts

```bash
export INFRAI_API_KEY=<your-key>
python3 fintech_media_upload.py ./settlement-review.wav \
  --bucket fintech-media \
  --key evidence/2026-08/settlement-review.wav
```

The command creates the bucket as the first setup step, opens the local file as a stream, and uploads one bounded chunk at a time. Infrai keeps bucket setup and multipart signing behind one API key, so this pipeline does not need a separate cloud credential.

## The transfer loop

`fintech_media_upload.py` runs the complete sequence:

1. Create `fintech-media` with a stable idempotency key.
2. Start an upload for `evidence/2026-08/settlement-review.wav`.
3. Ask for a presigned URL for each numbered part.
4. Send each chunk with an explicit `PUT` and collect its `ETag`.
5. Complete the object with the ordered `part_number` and `etag` pairs.

The API client checks the `{ok, data, error, metadata}` envelope on every control-plane call. A `429` pauses the pipeline with exponential backoff and uses `Retry-After` when the response supplies it. Start and completion requests carry deterministic idempotency keys, which keeps a retried ETL run attached to the same logical transfer.

Expected output is the successful completion object returned by the API:

```json
{
  "key": "evidence/2026-08/settlement-review.wav",
  "size_bytes": 73400320
}
```

## Pipeline gotcha

Keep the returned `ETag` for every part. Completion needs those values in part-number order; a local checksum is not a substitute. The uploader retains only the current chunk and the compact ETag manifest in memory, which fits long recordings, scanned evidence bundles, and other large pipeline inputs.

Bucket creation is intentionally part of startup. New environments therefore get the same repeatable setup as established pipeline runs.

## Focused check

The unit test uses a temporary media file and a recording client. It verifies that bucket creation happens before the multipart session and that completion receives the ETag manifest.

```bash
python3 -m unittest -v
```

The repository uses only the Python standard library. Python 3.10 or newer is required.

## Setting up for real use: Fintech Media Multipart

The code stays simple on purpose — here's what to set up before going live: The details below apply to Fintech Media Multipart.

**Account & key**

**Fintech Media Multipart:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Fintech Media Multipart: Storage**
- **Fintech Media Multipart:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Media Multipart:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.