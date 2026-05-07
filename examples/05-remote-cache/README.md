# 05 · remote-cache

A shared cache that multiple clones read through and write through.
`local-fs` here; swap `type = "s3"` (or `http` / `gcs`) for a real team.

## Run

```bash
echo "hello from the first clone" > input.txt
rm -rf .ntask /tmp/ntask-team-cache
ntask transform                   # ~2s - cache miss; writes to local + /tmp cache
ntask transform                   # instant - local hit
```

Now simulate a fresh clone:

```bash
rm -rf .ntask                     # wipe LOCAL cache only
ntask transform                   # instant - local miss, remote HIT, output.txt restored
```

## What to notice

- `[tool.ntask.remote_cache]` in `pyproject.toml` is the only config
  needed. No environment variables, no daemon.
- The flow is **read-through + write-through**:
  1. Local cache consulted first.
  2. Local miss → consult remote. Remote hit → restore `outputs/` and
     populate local. Remote miss → run the task, then store entry + outputs
     blob to **both** local and remote.
- Remote output blobs are deterministic `tar.gz` files keyed by the
  `outputs_hash`. Sorted entries + mtime=0 means two different tasks that
  produce identical output share the same blob.
- Remote failures (network blip, auth glitch) **warn once then silently
  fall back to local**. Builds never fail because the cache backend is
  flaky.
- `ntask --offline transform` skips the remote entirely for this run.

## Real backends

All string fields expand `$VAR` references at load time, so credentials
stay out of `pyproject.toml`.

```toml
# S3 (pip install ntask[s3])
[tool.ntask.remote_cache]
type = "s3"
bucket = "my-team-build-cache"
prefix = "ntask/"
# endpoint_url = "https://minio.internal"   # optional, for MinIO / R2 / B2

# GCS (pip install ntask[gcs])
[tool.ntask.remote_cache]
type = "gcs"
bucket = "my-team-build-cache"
prefix = "ntask/"

# HTTP (core; any server that honors GET + PUT)
[tool.ntask.remote_cache]
type = "http"
url = "https://cache.internal/ntask"
auth_header = "Bearer $CACHE_TOKEN"
```
