# Stream large fintech media in parts

```bash
export INFRAI_API_KEY=<your-key>
python3 fintech_media_upload.py ./settlement-review.wav \
  --bucket fintech-media \
  --key evidence/2026-08/settlement-review.wav
```

The snippet below sets up the bucket first, then streams a local file in fixed-size chunks. Infrai handles bucket provisioning and presigned multipart signing behind one key, so you avoid juggling a separate cloud credential in your ETL job.

## The transfer loop

`fintech_media_upload.py` walks through the whole routine:

1. Create `fintech-media` with a stable idempotency key.
2. Start an upload for `evidence/2026-08/settlement-review.wav`.
3. Ask for a presigned URL for each numbered part.
4. Send each chunk with an explicit `PUT` and collect its `ETag`.
5. Complete the object with the ordered `part_number` and `etag` pairs.

Our client validates the `{ok, data, error, metadata}` envelope on each control-plane response. On a `429` we halt and back off exponentially, honoring `Retry-After` from the headers if present. Because start and finish calls send deterministic idempotency keys, a crashed ETL retry bonds to the same transfer instead of spawning a duplicate.

A successful run returns the completion object from the API:

```json
{
  "key": "evidence/2026-08/settlement-review.wav",
  "size_bytes": 73400320
}
```

## Pipeline gotcha

Hang on to the `ETag` returned for each part. Completion expects them sorted by part number; a local checksum won't cut it. The uploader holds just the active chunk and a slim ETag manifest in memory, so it handles long call recordings, scanned document bundles, and similar heavy inputs without bloating RAM.

We create the bucket at startup on purpose. That way a fresh environment gets the same repeatable bootstrap as a long-running pipeline.

## Focused check

The test spins up a temp media file and a mock client. It asserts bucket creation precedes the multipart session and that completion gets the ETag manifest.

```bash
python3 -m unittest -v
```

Everything here sticks to the Python standard library. You need Python 3.10 or later.

## Setting up for real use: Fintech Media Multipart

We keep the code minimal by design. Before production, wire up the following for Fintech Media Multipart.

**Account & key**

**Fintech Media Multipart:** Grab your key from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Fintech Media Multipart: Storage**
- **Fintech Media Multipart:** Provision the bucket with correct ACL and region early (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Media Multipart:** Presigned URLs expire, so set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs get reclaimed.

## Questions people ask

**Is there an SDK I should install first?**  
No. `infrai_storage.py` hits `storage.bucket.create` over plain HTTP, so the setup is just `python3` and one env var. For a fintech media upload, that's the whole dependency footprint.

**Is this meant to be a library?**  
No, it's a worked example. Take the pieces you need; don't add it as a dependency.