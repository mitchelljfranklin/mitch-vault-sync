# AGENTS.md

## What this is

Docker-based Python app that one-way syncs a self-hosted Vaultwarden vault to Bitwarden cloud on a schedule. Entrypoint is `sync.py`; phases live in `src/exporter.py` and `src/importer.py`, sharing the CLI runner in `src/bw_cli.py`. Both phases shell out to the Bitwarden CLI (`bw`) via `subprocess`.

## Verify changes

There is no test suite. Syntax check only:

```
python -m py_compile sync.py src/exporter.py src/importer.py src/bw_cli.py
```

On this Windows machine `python3` is a broken Store alias — use `python` or `& "C:\Program Files\Python314\python.exe"`.

Real verification is manual: `docker compose up --build`, watch `docker compose logs -f`, confirm the "Import verified: X/X items" line. Set `LOG_LEVEL=DEBUG` in `.env` for per-command tracing.

## Bitwarden CLI gotchas (cost us hours — do not regress)

- Export/import are **single bulk calls**: `bw export --format json --output <path> --session S` and `bw import bitwardenjson <path> --session S`. The bitwardenjson importer consumes exactly the export format and rebuilds folders itself — do not reintroduce per-item `bw create` loops; if you ever do, note that `create`/`edit` take Base64-encoded JSON via `bw encode`, not plain JSON.
- API keys authenticate **login only**. Unlocking/decrypting always needs the master password via `bw unlock --passwordenv BW_PASSWORD`. There is no `--apikey` option for `unlock`.
- Vaultwarden does **not** support personal API keys at all — source side uses email/password only (`VAULTWARDEN_EMAIL`/`VAULTWARDEN_PASSWORD`). Only the Bitwarden cloud target uses API keys.
- Deletes must use `--permanent`; soft-deleted items pile into the cloud Trash (~400+ per daily sync) because import merges rather than replaces, so a clear phase is always required first.
- **List filters lie.** In CLI 2026.x the plain `list items` hides archived ciphers, and the `--archived` filter is unreliable after imports (it can return every item with `archivedDate: null`, then self-correct minutes later). Never verify or enumerate against filtered lists: the clear phase enumerates via a throwaway target export (`/data/clear_snapshot.json`), and verification compares the plain list count against export-derived expected-visible (`total − archived`). `bw get item <name>` also hides archived items.
- Archived state survives bitwardenjson import intact (`archivedDate` carried) — verified live; do not strip that field.
- Session keys in command args are masked by `format_cli_arguments()` in `src/bw_cli.py` — route any new CLI logging/error text through it or keys leak into logs.
- "Not found" errors during deletes are treated as success on purpose: stale snapshots and laggy indexes make already-vanished items normal.
- `BW_VERSION` is pinned in the **Dockerfile** (authoritative ARG); the docker-compose build-arg block is commented out and only matters for local source builds — update both together if you touch them.
- Arch selection uses buildx's `TARGETARCH` (`amd64`/`arm64`) with a `--platform=$BUILDPLATFORM` base, so multi-arch builds run natively without QEMU. No ARMv7 binaries exist for CLI 2026.x; only amd64 and arm64 are built.
- Releases are published to GHCR by `.github/workflows/release.yml`: on release publish it tags `<version>` + `latest`; manual dispatch exists in the Actions tab. The workflow refuses to build if the pinned CLI's `bw-linux` / `bw-linux-arm64` zips are missing from the GitHub release.
- Check latest CLI version at `https://api.github.com/repos/bitwarden/clients/releases/tags/cli-v<VERSION>` — verify the `bw-linux-<VERSION>.zip` asset exists before pinning.

## Sync semantics

Import is **full replace**: `_clear_vault()` permanently deletes every item and folder in the Bitwarden cloud vault (enumerated via a throwaway target export so archived items are included) before importing. Never point a test run at a real Bitwarden account you care about. The importer fails the cycle unless the post-import plain-list count equals the export-derived visible expectation. `/data/vault_export.json` is plaintext decrypted vault data and is deleted in the importer's `finally` block.

## Code style (hard requirement, enforced in review)

Per `CONTRIBUTING.md`: no abbreviated variable names — spell them out (`master_password`, not `mp`; `error_message`, not `err`). Log/error messages are complete grammatical English sentences with counts, durations, and units spelled out ("waiting 4 seconds", not "4s"). Comments explain *why*, never *what*.

## Secrets

Credentials live either as literals in the `docker-compose.yml` `environment` block (the default setup) or as `${VAR}` references backed by `.env` (`.gitignore` covers `.env` and `.env.*`). Never echo credential values into logs; never commit real credentials in the compose file — keep placeholder examples there and put production values only in untracked files or the deployed copy. `data/vault_export.json` contains the fully decrypted vault during a sync cycle; it is gitignored too.
