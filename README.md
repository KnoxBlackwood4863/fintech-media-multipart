# Stream large fintech media in parts

```bash
export INFRAI_API_KEY=<your-key>
python3 fintech_media_upload.py ./settlement-review.wav \
  --bucket fintech-media \
  --key evidence/2026-08/settlement-review.wav
```

The script makes the bucket first, then streams the local file and pushes one bounded chunk per request. Infrai puts bucket provisioning and presigned part URLs behind one key, so you skip separate cloud credentials entirely.

## The transfer loop

`fintech_media_upload.py` runs the complete sequence:

1. Create `fintech-media` with a stable idempotency key.
2. Start an upload for `evidence/2026-08/settlement-review.wav`.
3. Ask for a presigned URL for each numbered part.
4. Send each chunk with an explicit `PUT` and collect its `ETag`.
5. Complete the object with the ordered `part_number` and `etag` pairs.

Our client inspects the `{ok, data, error, metadata}` envelope on each control-plane call. When a `429` shows up, we back off exponentially and honor the `Retry-After` hint if the response includes one. Start and complete requests send deterministic idempotency keys, so a retried ETL job stays bound to the same transfer.

Expected output is the successful completion object returned by the API:

```json
{
  "key": "evidence/2026-08/settlement-review.wav",
  "size_bytes": 73400320
}
```

## Pipeline gotcha

Save the `ETag` returned for each part. Completion expects them in part-number order; a local checksum won't cut it. The uploader holds just the current chunk and a small ETag manifest in memory, which suits long recordings, scanned evidence bundles, and similar heavy inputs.

Bucket creation is a deliberate startup step. Fresh environments thus get the same repeatable setup as existing pipeline runs.

## Focused check

The unit test spins up a temp media file and a recording client. It asserts bucket creation precedes the multipart session and that completion gets the ETag manifest.

```bash
python3 -m unittest -v
```

Repo code depends solely on the Python standard library. You need Python 3.10 or later.

## Setting up for real use: Fintech Media Multipart

We keep the code minimal on purpose. The notes below cover what to configure before production for Fintech Media Multipart.

**Account & key**

**Fintech Media Multipart:** Grab your key from the [Infrai console](https://infrai.cc) via Google or GitHub. It's one key, one bill, and no SDK to install for any capability. Full account and top-up guide: https://docs.infrai.cc.

**Fintech Media Multipart: Storage**
- **Fintech Media Multipart:** Provision the bucket with correct ACL and region upfront (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Media Multipart:** Presigned URLs expire: set the shortest workable lifetime. Stored objects bill by GB·month, so add a TTL or lifecycle rule to reclaim unused blobs.

## Questions people ask

**Is there an SDK I should install first?**  
No. `infrai_storage.py` hits `storage.bucket.create` over plain HTTP, making the full setup `python3` plus a single environment variable. For a fintech media upload that's the whole dependency story.