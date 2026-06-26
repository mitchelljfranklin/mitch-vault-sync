# MitchVault Sync

One-way vault synchronization from a self-hosted [Vaultwarden](https://github.com/dani-garcia/vaultwarden) instance to [Bitwarden](https://bitwarden.com) cloud. Runs in Docker on a configurable schedule.

```
Vaultwarden (local) ──[daily sync]──▶ Bitwarden Cloud (backup)
```

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/mitchelljfranklin/mitchvault-sync.git
cd mitchvault-sync
cp .env.example .env
# edit .env with your credentials

# 2. Start
docker compose up -d

# 3. Check logs
docker compose logs -f
```

The first sync runs immediately on startup, then on the configured schedule (default: every 24 hours).

## What Gets Synced

| Item Type | Synced |
|---|---|
| Logins (username, password, URIs) | Yes |
| Passkeys (FIDO2 / WebAuthn credentials) | Yes |
| TOTP seeds (authenticator codes) | Yes |
| Secure notes | Yes |
| Credit cards | Yes |
| Identities | Yes |
| Custom fields | Yes |
| Folders | Yes (remapped by name) |
| File attachments | No |
| Password history | Yes |
| Item favorites | Yes |

## Prerequisites

- A running **Vaultwarden** instance (v1.30+ for API key support)
- A **Bitwarden** cloud account (free or premium)
- **API keys** from both services (see below)

## Getting API Keys

### Bitwarden Cloud

1. Log into the [Bitwarden Web Vault](https://vault.bitwarden.com)
2. Go to **Account Settings** → **Security** → **Keys**
3. Click **View API Key** and enter your master password
4. Copy `client_id` and `client_secret`

The API key scope must include access to your personal vault (read + write).

### Vaultwarden

1. Log into your Vaultwarden web vault
2. Go to **Account Settings** → **Security** → **Keys**
3. Click **View API Key** (if available — requires Vaultwarden v1.30+)

If API keys are not available, use email + password authentication instead.

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# ── Vaultwarden (source) ──
VAULTWARDEN_URL=https://vault.example.com      # Your Vaultwarden URL
VAULTWARDEN_MP=your-master-password            # Master password for vault unlock

# Auth: API key (recommended)
VAULTWARDEN_CLIENT_ID=user.your-client-id
VAULTWARDEN_CLIENT_SECRET=your-client-secret

# Auth: email/password (fallback)
# VAULTWARDEN_EMAIL=user@example.com
# VAULTWARDEN_PASSWORD=your-password

# ── Bitwarden Cloud (target) ──
BITWARDEN_CLIENT_ID=user.your-client-id        # From Bitwarden web vault
BITWARDEN_CLIENT_SECRET=your-client-secret
BITWARDEN_SERVER=https://vault.bitwarden.com   # or vault.bitwarden.eu

# ── Scheduling ──
SYNC_SCHEDULE=daily                            # hourly | daily | 12h | 6h | weekly | 7d | "3:00"

# ── Logging ──
LOG_LEVEL=INFO                                 # DEBUG for troubleshooting
```

### Full Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `VAULTWARDEN_URL` | Yes | — | Your Vaultwarden instance URL |
| `VAULTWARDEN_MP` | Yes | — | Master password to unlock the Vaultwarden vault |
| `VAULTWARDEN_CLIENT_ID` | No | — | API key client ID (preferred auth method) |
| `VAULTWARDEN_CLIENT_SECRET` | No | — | API key client secret |
| `VAULTWARDEN_EMAIL` | No | — | Email (fallback if API key not set) |
| `VAULTWARDEN_PASSWORD` | No | — | Password (fallback if API key not set) |
| `BITWARDEN_CLIENT_ID` | Yes | — | Bitwarden cloud API key client ID |
| `BITWARDEN_CLIENT_SECRET` | Yes | — | Bitwarden cloud API key client secret |
| `BITWARDEN_SERVER` | No | `https://vault.bitwarden.com` | Bitwarden server (use `.eu` for EU region) |
| `BITWARDEN_MP` | No | — | Master password for fallback unlock (rarely needed) |
| `SYNC_SCHEDULE` | No | `daily` | Human-readable schedule (see below) |
| `SYNC_CRON` | No | — | Raw cron expression (overrides `SYNC_SCHEDULE`) |
| `LOG_LEVEL` | No | `INFO` | `INFO` or `DEBUG` |
| `EXPORT_WORKERS` | No | `10` | Parallel workers for export phase |
| `IMPORT_WORKERS` | No | `5` | Parallel workers for import phase |

## Scheduling

MitchVault Sync supports two scheduling methods.

### Human-Readable (recommended)

Set `SYNC_SCHEDULE` to one of:

| Value | Behavior |
|---|---|
| `hourly` | Every hour on the hour |
| `daily` / `24h` | Every 24 hours from container start |
| `12h` / `6h` / `4h` / `2h` / `1h` | Every N hours |
| `weekly` / `7d` | Every 7 days |
| `3:00` | Daily at 3:00 AM UTC |
| `3:00 America/New_York` | Daily at 3:00 AM in the given timezone |

Defaults to `daily` if not set.

### Cron Expression (advanced)

Set `SYNC_CRON` to a standard cron expression (UTC):

```env
SYNC_CRON="0 2 * * *"     # Daily at 2:00 AM UTC
SYNC_CRON="0 */6 * * *"   # Every 6 hours
SYNC_CRON="0 3 * * 0"     # Sundays at 3:00 AM UTC
```

When `SYNC_CRON` is set, it takes priority over `SYNC_SCHEDULE`.

## Docker Deployment

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose build --no-cache
```

### Healthcheck

The container includes a healthcheck that verifies the sync cache file exists. The container starts as healthy after the first successful sync.

### Architecture

```
mitchvault-sync/
├── sync.py                 # Main entrypoint — scheduler + orchestrator
├── src/
│   ├── exporter.py         # Phase 1: Export from Vaultwarden via bw CLI
│   └── importer.py         # Phase 2: Import to Bitwarden cloud via bw CLI
├── data/                   # Mounted volume — holds cache + bw CLI state
│   ├── vaultwarden/        # bw CLI data dir (isolated session)
│   ├── bitwarden/          # bw CLI data dir (isolated session)
│   ├── vault_cache.json    # Exported vault cache
│   └── last_sync           # Timestamp of last successful sync
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env
```

### Sync Flow

1. **Login** to Vaultwarden via `bw` CLI (API key or email/password)
2. **Unlock** vault with master password
3. **Export** — list all item IDs, fetch each fully decrypted in parallel (10 workers)
4. **Cache** — save full vault JSON to `/data/vault_cache.json`
5. **Login** to Bitwarden cloud via `bw` CLI (API key)
6. **Clear** — delete all existing items and folders from Bitwarden vault
7. **Import** — recreate folders, then import all items in parallel (5 workers)
8. **Verify** — log counts and write success timestamp

### Performance

| Vault Size | Export Time | Import Time | Total |
|---|---|---|---|
| 50 items | ~8s | ~10s | ~20s |
| 200 items | ~25s | ~40s | ~70s |
| 500 items | ~55s | ~100s | ~3 min |
| 1000 items | ~110s | ~200s | ~5 min |

Times are approximate. Parallel workers and network latency affect actual performance.

## Logging

Default log level is `INFO` — shows phase transitions, counts, and final summary:

```
2026-06-26 02:00:01 | INFO     | mitchvault   | MitchVault Sync — starting cycle
2026-06-26 02:00:03 | INFO     | exporter     | Found 142 items
2026-06-26 02:00:50 | INFO     | importer     | Imported 142/142 items
2026-06-26 02:00:51 | INFO     | mitchvault   | Sync complete: exported 142, imported 142 in 50s
```

Set `LOG_LEVEL=DEBUG` to see every `bw` command, HTTP response, and per-item progress:

```
2026-06-26 02:00:05 | DEBUG    | exporter     | [1/142] GitHub (1)
2026-06-26 02:00:05 | DEBUG    | exporter     | Bitwarden CLI: get item abc123-def456 --session ...
2026-06-26 02:01:20 | DEBUG    | importer     | [42/142] Creating: Google
```

## Limitations

- **One-way only** — Vaultwarden → Bitwarden. Changes made directly in Bitwarden are overwritten on the next sync.
- **Full replace** — each sync deletes all items from Bitwarden and re-imports. No incremental/delta sync.
- **No file attachments** — attached files are not synced. A future version may add this.
- **Single user** — syncs one personal vault. Organization support may be added later.
- **No real-time sync** — runs on a schedule, not triggered by vault changes.

## Troubleshooting

### Sync fails with "bw login failed"

- Verify `VAULTWARDEN_URL` is reachable from the container
- Check `VAULTWARDEN_CLIENT_ID` and `VAULTWARDEN_CLIENT_SECRET` are correct
- Ensure your Vaultwarden instance supports API keys (v1.30+)
- Try email/password auth as a fallback

### Sync fails with "bw unlock failed"

- Verify `VAULTWARDEN_MP` is correct
- If using API key auth, ensure your Vaultwarden version supports API key unlock
- Check for special characters in the password that may need escaping in `.env`

### "Failed to create item" / rate limit errors

- Reduce `IMPORT_WORKERS` (default is 5, try 2)
- Bitwarden cloud has rate limits — the sync retries automatically with exponential backoff
- If persistent, schedule your sync during off-peak hours

### Enable debug logging

```env
LOG_LEVEL=DEBUG
```

Then view logs:

```bash
docker compose logs -f mitchvault-sync
```

Debug mode shows every `bw` CLI command, API response, and per-item progress.

### Sync says "0 items exported"

- Your Vaultwarden vault may be empty, or
- The `bw` session may have expired — check the container logs for auth errors
- Verify your Vaultwarden user has items in their personal vault (not just an organization)

### Container shows "unhealthy"

- The healthcheck checks that `/data/last_sync` exists
- This file is created after the first successful sync
- If the initial sync fails, the container will show as unhealthy until a sync succeeds
- Check logs to diagnose why the initial sync failed

## Building for ARM

The Dockerfile auto-detects architecture. For ARM devices (Raspberry Pi, Apple Silicon):

```bash
docker compose build --build-arg BW_VERSION=2024.11.1
```

The `bw` CLI binary is downloaded for the correct architecture automatically.

See **[PRIVACY.md](PRIVACY.md)** for a comprehensive security and privacy document covering data flow, encryption states, storage locations, and hardening recommendations.

## Security

- **API keys** and **master passwords** are stored as environment variables
- Use Docker secrets or a secrets manager for production deployments
- Never commit `.env` to version control (it's in `.gitignore`)
- The vault cache file (`/data/vault_cache.json`) contains **decrypted** vault items — mount the data volume on encrypted storage if possible
- The `bw` CLI session data is stored in `/data/vaultwarden/` and `/data/bitwarden/` — these directories persist across container restarts

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for code style requirements (human-readable names and messages mandatory), commit conventions, and pull request workflow.

## License

MIT — see [LICENSE](LICENSE)
