# AGENTS.md

## What this is

Docker-based Python app that one-way syncs a self-hosted Vaultwarden vault to Bitwarden cloud on a schedule. Entrypoint is `sync.py`; phases live in `src/exporter.py` and `src/importer.py`, sharing the CLI runner in `src/bw_cli.py`. Both phases shell out to the Bitwarden CLI (`bw`) via `subprocess`. The scheduler runs one sync immediately at container startup, then on the configured schedule. The Dockerfile copies only `sync.py` and `src/` into the image, so any new top-level module must be added there.

## Verify changes

There is no test suite. Syntax check only (list files explicitly — PowerShell and cmd do not expand `src/*.py`):

```
python -m py_compile sync.py src/bitwarden_api.py src/bw_cli.py src/exporter.py src/importer.py src/logger.py
```

On this Windows machine `python3` is a broken Store alias — use `python` or `& "C:\Program Files\Python314\python.exe"`. The app cannot run natively: `/data/...` paths and the `bw` binary are container-only.

Real verification is manual, and **`docker compose up --build` does not test your edits by default**: `docker-compose.yml` ships with `image:` set and the `build:` block commented out, so Compose runs the published image. To test local code, comment out `image:`, uncomment `build:` (its `BW_VERSION` must match the Dockerfile `ARG`), then `docker compose up -d --build` and watch `docker compose logs -f` for "Import verified" and "Sync complete". Any real run permanently wipes the target vault before importing — use a throwaway Bitwarden account.

`LOG_LEVEL` is a literal in the compose `environment` block, and the compose file has no `${VAR}` references, so **editing `.env` alone does nothing**. Change the compose value (or convert the key to `${LOG_LEVEL}`). `SYNC_CRON` overrides `SYNC_SCHEDULE`; unrecognized schedules log a warning and fall back to daily.

## Bitwarden CLI gotchas (cost us hours — do not regress)

- Export/import are **single bulk calls**: `bw export --format json --output <path> --session S` and `bw import bitwardenjson <path> --session S`. The bitwardenjson importer consumes exactly the export format and rebuilds folders itself — do not reintroduce per-item `bw create` loops; if you ever do, note that `create`/`edit` take Base64-encoded JSON via `bw encode`, not plain JSON.
- API keys authenticate **login only**. Unlocking/decrypting always needs the master password via `bw unlock --passwordenv BW_PASSWORD`. There is no `--apikey` option for `unlock`.
- Vaultwarden does **not** support personal API keys at all — source side uses email/password only (`VAULTWARDEN_EMAIL`/`VAULTWARDEN_PASSWORD`). Only the Bitwarden cloud target uses API keys.
- Deletes must use `--permanent`; soft-deleted items pile into the cloud Trash (~400+ per daily sync) because import merges rather than replaces, so a clear phase is always required first.
- **`bw list` and `bw export` read the local CLI cache, not the server.** `bw login` performs a forced full sync, which makes the exporter and the initial clear snapshot fresh, but `bw import` starts its own background sync without awaiting it. Always run `bw sync --force` before counting after a mutation; verification does this on every attempt.
- **List filters lie.** In CLI 2026.x the plain `list items` hides archived ciphers, and the `--archived` filter is unreliable after imports (it can return every item with `archivedDate: null`, then self-correct minutes later). Never enumerate the clear phase with `list`: it uses a throwaway target export (`/data/clear_snapshot.json`), and verification compares the post-sync plain list count against export-derived expected-visible (`total − archived`). `bw get item <name>` also hides archived items.
- **Clear prefers the bulk API and falls back to the serial CLI.** `_clear_vault_via_api()` authenticates with the personal API key, reads `/api/sync`, and permanently deletes ciphers and folders in 500-ID chunks; any failure logs a warning and runs `_clear_vault_via_cli()`. The token endpoint requires a `Bitwarden-Client-Version` header (taken from `bw --version`). Never log the access token, client secret, or request headers. The client API is internal and undocumented, so the fallback is mandatory.
- **Serial deletion is the fallback, not the default.** It runs one `bw` process per item with `DELETE_DELAY_SECONDS` and `_run_with_retry()` backoff, because concurrent `bw` processes contend for one `BW_DATA_DIR` and Bitwarden Cloud rate-limits bulk deletes (observed 429s, DNS failures, and 120-second timeouts). Measured throughput is roughly one item every four seconds (~30 minutes for a 388-item vault); the bulk API path clears the same vault in about six seconds.
- `_clear_vault()` verifies the vault is actually empty (sync, export, plus trash list) before importing, retrying deletions for up to three rounds and aborting otherwise. Keep this check: importing into a dirty vault creates duplicates that make every following cycle worse.
- Archived state survives bitwardenjson import intact (`archivedDate` carried) — verified live; do not strip that field.
- Session keys in command args are masked by `format_cli_arguments()` in `src/bw_cli.py`. `_run()` also converts `subprocess.TimeoutExpired` into a sanitized `RuntimeError`, because `TimeoutExpired` embeds the raw command and once leaked a live session key. Never log raw subprocess exceptions; route new CLI logging/error text through the masking helper.
- The "Import verified" log now reports `visible/expected-visible`; `imported_count` returned to `sync.py` is also the visible count, not the export total.
- "Not found" errors during deletes are treated as success on purpose: stale snapshots and laggy indexes make already-vanished items normal.
- `BW_VERSION` is pinned in the **Dockerfile** (authoritative ARG) and duplicated in the commented compose `build:` block; keep both identical when bumping. The release workflow greps the Dockerfile value and refuses to build if the matching `bw-linux-<version>.zip` / `bw-linux-arm64-<version>.zip` assets are absent.
- Multi-arch builds use buildx `TARGETARCH` (`amd64`/`arm64`) on a `--platform=$BUILDPLATFORM` base, so they run natively without QEMU. Only those two architectures are built: no ARMv7 `bw` binaries exist, so 32-bit Raspberry Pi is unsupported.
- Releases are published to GHCR by `.github/workflows/release.yml`: publishing a GitHub release tags `<version>` + `latest`; a manual dispatch publishes only `custom_tag` and does **not** move `latest` unless `publish_latest` is checked. Check CLI versions at `https://api.github.com/repos/bitwarden/clients/releases/tags/cli-v<VERSION>` before pinning.

## Sync semantics

Import is **full replace**: `_clear_vault()` permanently deletes every item and folder in the Bitwarden cloud vault (bulk API when available, per-item CLI fallback otherwise), plus anything in the Trash, then verifies the vault is empty before importing. It enumerates via a throwaway target export because archived ciphers are otherwise invisible. Clear runs before import, so any failure in that window leaves the target empty or partial; `/data/last_sync` is only written after full success, so the healthcheck eventually turns unhealthy. Import merges, so a failed delete becomes a duplicate on the next cycle. The importer fails the cycle unless the post-import plain-list count (after an explicit `bw sync --force`) equals the export-derived visible expectation (`total − archived`). `/data/vault_export.json`, `/data/clear_snapshot.json`, and `/data/bitwarden_device_id` live under `/data`; the export is removed in the importer's `finally` block and each snapshot right after it is read.

## Code style (hard requirement, enforced in review)

Per `CONTRIBUTING.md`: no abbreviated variable names — spell them out (`master_password`, not `mp`; `error_message`, not `err`). Log/error messages are complete grammatical English sentences with counts, durations, and units spelled out ("waiting 4 seconds", not "4s"). Comments explain *why*, never *what*. Existing log calls use lazy `%s` arguments rather than f-strings; raised error messages use f-strings.

## Secrets

Credentials are literals in the `docker-compose.yml` `environment` block by default; `.env` only takes effect if you replace literals with `${VAR}` references (`.gitignore` covers `.env` and `.env.*`). Never echo credential values into logs; never commit real credentials in the compose file — keep placeholder examples there and put production values only in untracked files or the deployed copy. The local `.env`, if present, may contain real credentials — do not print or commit it. `data/` holds decrypted exports and CLI session state during a cycle and is gitignored.
