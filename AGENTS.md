# AGENTS.md

## What this is

Docker-based Python app that one-way syncs a self-hosted Vaultwarden vault to Bitwarden cloud on a schedule. Entrypoint is `sync.py`; phases live in `src/exporter.py` and `src/importer.py`. Both phases shell out to the Bitwarden CLI (`bw`) via `subprocess`.

## Verify changes

There is no test suite. Syntax check only:

```
python -m py_compile sync.py src/exporter.py src/importer.py
```

On this Windows machine `python3` is a broken Store alias — use `python` or `& "C:\Program Files\Python314\python.exe"`.

Real verification is manual: `docker compose up --build`, watch `docker compose logs -f`, confirm item counts match. Set `LOG_LEVEL=DEBUG` in `.env` for per-item tracing.

## Bitwarden CLI gotchas (cost us hours — do not regress)

- `bw create item` and `bw create folder` take **Base64-encoded JSON**, not plain JSON. Always pipe through `bw encode` first, then pass the encoded output as stdin to `create`. Raw JSON fails server-side with "Error parsing the encoded request data" — which looks like a data problem but isn't.
- API keys authenticate **login only**. Unlocking/decrypting always needs the master password via `bw unlock --passwordenv BW_PASSWORD`. There is no `--apikey` option for `unlock`.
- Vaultwarden does **not** support personal API keys at all — source side uses email/password only (`VAULTWARDEN_EMAIL`/`VAULTWARDEN_PASSWORD`). Only the Bitwarden cloud target uses API keys.
- `BW_VERSION` is pinned in **both** `Dockerfile` (ARG) and `docker-compose.yml` (build arg) — update both together.
- No ARMv7 binaries exist for CLI 2026.x; Dockerfile only handles x86_64 and arm64.
- Check latest CLI version at `https://api.github.com/repos/bitwarden/clients/releases/tags/cli-v<VERSION>` — verify the `bw-linux-<VERSION>.zip` asset exists before pinning.

## Sync semantics

Import is **full replace**: `_clear_vault()` deletes every item and folder in the Bitwarden cloud vault before re-importing. Never point a test run at a real Bitwarden account you care about. Items are sanitized before creation: top-level server fields (`id`, `revisionDate`, etc.), `attachments`, and fido2 credential ids are stripped; `folderId` is remapped to newly created folder IDs.

## Code style (hard requirement, enforced in review)

Per `CONTRIBUTING.md`: no abbreviated variable names — spell them out (`master_password`, not `mp`; `error_message`, not `err`). Log/error messages are complete grammatical English sentences with counts, durations, and units spelled out ("waiting 4 seconds", not "4s"). Comments explain *why*, never *what*.

## Secrets

`.env` holds master passwords and API keys in plaintext; `.gitignore` covers `.env` and `.env.*` — never commit it or echo its contents into logs. `data/vault_cache.json` contains the fully decrypted vault; it is gitignored too.
