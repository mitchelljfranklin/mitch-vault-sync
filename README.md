# MitchVault Sync

![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-ready-brightgreen)
![Platform](https://img.shields.io/badge/platform-linux%2Farm-lightgrey)
[![PRs Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen)](CONTRIBUTING.md)

> Your Vaultwarden vault. Backed up to Bitwarden. Every day. Automatically.

Keep your self-hosted passwords safe in the cloud. MitchVault Sync mirrors your local [Vaultwarden](https://github.com/dani-garcia/vaultwarden) vault to [Bitwarden](https://bitwarden.com) cloud — no manual exports, no missed items, passkeys included.

```
                         MitchVault Sync
┌──────────────────┐     ┌─────────────────────────┐     ┌──────────────────┐
│   Vaultwarden    │────▶│  ┌─────────┐ ┌────────┐  │────▶│  Bitwarden Cloud │
│    (your LAN)    │     │  │ export  │ │ import │  │     │    (backup)      │
│                  │     │  │ 10 workers│ │ 5 workers│ │     │                  │
└──────────────────┘     │  └─────────┘ └────────┘  │     └──────────────────┘
                         │       cron: daily         │
                         └─────────────────────────┘
```

---

## Contents

- [Why?](#why)
- [Quick Start](#quick-start)
- [What Gets Synced](#what-gets-synced)
- [Prerequisites](#prerequisites)
- [Getting API Keys](#getting-api-keys)
- [Configuration](#configuration)
- [Scheduling](#scheduling)
- [Docker Deployment](#docker-deployment)
- [Logging](#logging)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [Building for ARM](#building-for-arm)
- [Security & Privacy](#security)
- [Contributing](#contributing)
- [License](#license)

---

## Why?

You self-host Vaultwarden for privacy and control. But what happens if the server dies, a disk fails, or your homelab takes an unexpected vacation?

MitchVault Sync gives you an always-fresh, always-encrypted copy of your vault in Bitwarden cloud. It runs on your schedule, handles every item type (including passkeys and TOTP seeds), and requires zero manual steps after setup.

| :lock: Problem | :key: Solution |
|---|---|
| No off-site backup | Mirrors every item to Bitwarden cloud |
| Manual exports are error-prone | Fully automated, runs on a schedule |
| Passkeys get left behind | FIDO2 credentials transfer intact |
| TOTP seeds require separate backup | Authenticator seeds are synced with their logins |
| DR plan requires remembering to export | Set it, forget it, check the logs |

### Feature Highlights

| Category | Capability |
|---|---|
| :bust_in_silhouette: Identity | Logins, passkeys, cards, identities — all item types |
| :key: Secrets | TOTP seeds, custom fields, password history |
| :file_folder: Organisation | Folders are recreated and items placed correctly |
| :zap: Speed | 10 export workers, 5 import workers — parallel by default |
| :clock1: Schedule | Human-readable (`daily`, `weekly`, `3:00`) or cron |
| :mag: Visibility | INFO logs for overview, DEBUG for per-item tracing |
| :lock: Security | API key auth, TLS everywhere, no telemetry, no third parties |
| :package: Deploy | Single `docker compose up -d`, runs on Pi, Synology, VPS |

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/mitchelljfranklin/mitchvault-sync.git
cd mitchvault-sync

# 2. Create your configuration
cp .env.example .env
# Open .env and fill in your Vaultwarden URL, API keys, and master password

# 3. Start the container
docker compose up -d

# 4. Watch the first sync
docker compose logs -f
```

> **Note**
> The first sync runs immediately on startup, then on your configured schedule. The default schedule is every 24 hours.

That's it. Your vault is now backing up automatically.

---

## What Gets Synced

| Item Type | Synced |
|---|---|
| Logins (username, password, URIs) | :white_check_mark: |
| Passkeys (FIDO2 / WebAuthn credentials) | :white_check_mark: |
| TOTP seeds (authenticator codes) | :white_check_mark: |
| Secure notes | :white_check_mark: |
| Credit cards | :white_check_mark: |
| Identities | :white_check_mark: |
| Custom fields | :white_check_mark: |
| Folders | :white_check_mark: (remapped by name) |
| Password history | :white_check_mark: |
| Item favorites | :white_check_mark: |
| File attachments | :x: |

---

## Prerequisites

- A running **Vaultwarden** instance (v1.30+ for API key support)
- A **Bitwarden** cloud account (free or premium)
- **API keys** from both services — see below
- **Docker** and **Docker Compose** installed on a machine that can reach both Vaultwarden and the internet
- The sync container runs anywhere Docker does — Raspberry Pi, Synology NAS, VPS, old laptop, your main desktop

---

## Getting API Keys

### Bitwarden Cloud

1. Log into the [Bitwarden Web Vault](https://vault.bitwarden.com)
2. Go to **Account Settings** > **Security** > **Keys**
3. Click **View API Key** and enter your master password
4. Copy the `client_id` and `client_secret`

> **Note**
> The API key must have scope to read and write your personal vault. These are created under your individual account settings.

### Vaultwarden

1. Log into your Vaultwarden web vault
2. Go to **Account Settings** > **Security** > **Keys**
3. Click **View API Key** (requires Vaultwarden v1.30+)

If API keys are not available on your Vaultwarden version, set `VAULTWARDEN_EMAIL` and `VAULTWARDEN_PASSWORD` in your `.env` file as a fallback.

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# ── Vaultwarden (source) ──────────────────────────────────
VAULTWARDEN_URL=https://vault.example.com
VAULTWARDEN_MP=your-master-password

# Auth: API key (recommended)
VAULTWARDEN_CLIENT_ID=user.your-client-id
VAULTWARDEN_CLIENT_SECRET=your-client-secret

# Auth: email/password (fallback — unset if using API key above)
# VAULTWARDEN_EMAIL=user@example.com
# VAULTWARDEN_PASSWORD=your-password

# ── Bitwarden Cloud (target) ──────────────────────────────
BITWARDEN_CLIENT_ID=user.your-client-id
BITWARDEN_CLIENT_SECRET=your-client-secret
BITWARDEN_SERVER=https://vault.bitwarden.com       # or vault.bitwarden.eu

# ── Scheduling ────────────────────────────────────────────
SYNC_SCHEDULE=daily       # hourly | daily | 12h | 6h | weekly | 7d | "3:00"

# ── Logging ───────────────────────────────────────────────
LOG_LEVEL=INFO            # DEBUG for troubleshooting
```

<details>
<summary><b>Full Environment Variable Reference</b> (click to expand)</summary>

| Variable | Required | Default | Description |
|---|---|---|---|
| `VAULTWARDEN_URL` | Yes | — | Your Vaultwarden instance URL |
| `VAULTWARDEN_MP` | Yes | — | Master password to unlock the Vaultwarden vault |
| `VAULTWARDEN_CLIENT_ID` | No | — | API key client ID (preferred authentication method) |
| `VAULTWARDEN_CLIENT_SECRET` | No | — | API key client secret |
| `VAULTWARDEN_EMAIL` | No | — | Email address (fallback if API key not set) |
| `VAULTWARDEN_PASSWORD` | No | — | Password (fallback if API key not set) |
| `BITWARDEN_CLIENT_ID` | Yes | — | Bitwarden cloud API key client ID |
| `BITWARDEN_CLIENT_SECRET` | Yes | — | Bitwarden cloud API key client secret |
| `BITWARDEN_SERVER` | No | `https://vault.bitwarden.com` | Bitwarden server — use `.eu` for EU region |
| `BITWARDEN_MP` | No | — | Master password for fallback unlock (rarely needed) |
| `SYNC_SCHEDULE` | No | `daily` | Human-readable schedule (see [Scheduling](#scheduling)) |
| `SYNC_CRON` | No | — | Raw cron expression — overrides `SYNC_SCHEDULE` |
| `LOG_LEVEL` | No | `INFO` | Log verbosity — `INFO` or `DEBUG` |
| `EXPORT_WORKERS` | No | `10` | Parallel workers for the export phase |
| `IMPORT_WORKERS` | No | `5` | Parallel workers for the import phase |

</details>

---

## Scheduling

MitchVault Sync supports two scheduling methods. Choose one.

### Human-Readable (recommended)

Set `SYNC_SCHEDULE` to any of these values:

| Value | Behavior |
|---|---|
| `hourly` | Every hour on the hour |
| `daily` / `24h` | Every 24 hours from container start |
| `12h` / `6h` / `4h` / `2h` / `1h` | Every N hours |
| `weekly` / `7d` | Every 7 days |
| `3:00` | Daily at 3:00 AM UTC |
| `3:00 America/New_York` | Daily at 3:00 AM in the named timezone |

Defaults to `daily` if not set.

### Cron Expression (advanced)

Set `SYNC_CRON` to a standard cron expression in UTC:

```env
SYNC_CRON="0 2 * * *"     # Daily at 2:00 AM UTC
SYNC_CRON="0 */6 * * *"   # Every 6 hours
SYNC_CRON="0 3 * * 0"     # Sundays at 3:00 AM UTC
```

When `SYNC_CRON` is set, it takes priority over `SYNC_SCHEDULE`.

---

## Docker Deployment

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after updating the code
docker compose build --no-cache
```

### Healthcheck

The container includes a built-in healthcheck. It verifies that the `/data/last_sync` file exists, which is created after the first successful sync. If the initial sync fails, the container will show as **unhealthy** until a sync succeeds.

### Architecture

```
mitchvault-sync/
├── sync.py                 # Entrypoint — scheduler and orchestrator
├── src/
│   ├── exporter.py         # Phase 1: Export from Vaultwarden via Bitwarden CLI
│   └── importer.py         # Phase 2: Import to Bitwarden cloud via Bitwarden CLI
├── data/                   # Mounted volume — cache and CLI state
│   ├── vaultwarden/        # Bitwarden CLI data directory (isolated session)
│   ├── bitwarden/          # Bitwarden CLI data directory (isolated session)
│   ├── vault_cache.json    # Exported vault cache
│   └── last_sync           # Timestamp of last successful sync
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── .env                    # Your configuration (never committed)
```

### Sync Flow

1. **Login** — Authenticate to Vaultwarden via Bitwarden CLI (API key or email/password)
2. **Unlock** — Decrypt the vault with your master password
3. **Export** — List all item IDs, fetch each fully decrypted in parallel (10 workers)
4. **Cache** — Save the full vault as JSON to `/data/vault_cache.json`
5. **Login** — Authenticate to Bitwarden cloud via Bitwarden CLI (API key)
6. **Clear** — Delete all existing items and folders from the Bitwarden vault
7. **Import** — Recreate folders, then import all items in parallel (5 workers)
8. **Verify** — Log the counts and write a success timestamp

### Performance

| Vault Size | Total Time |
|---|---|
| 50 items | ~20 seconds |
| 200 items | ~70 seconds |
| 500 items | ~3 minutes |
| 1000 items | ~5 minutes |

Times are approximate. Network latency and parallel worker counts affect actual performance.

> **Tip**
> If the import is slower than expected, check your logs for rate limit warnings. Reduce `IMPORT_WORKERS` if needed.

---

## Logging

Default log level is `INFO`. You will see phase transitions, item counts, and a final summary:

```
2026-06-26 02:00:01 | INFO     | mitchvault   | MitchVault Sync — starting cycle
2026-06-26 02:00:03 | INFO     | exporter     | Found 142 items
2026-06-26 02:00:50 | INFO     | importer     | Imported 142/142 items
2026-06-26 02:00:51 | INFO     | mitchvault   | Sync complete: exported 142, imported 142 in 50s
```

Set `LOG_LEVEL=DEBUG` for per-item progress and every Bitwarden CLI command:

```
2026-06-26 02:00:05 | DEBUG    | exporter     | [1/142] GitHub
2026-06-26 02:00:05 | DEBUG    | exporter     | Bitwarden CLI: get item abc123-def456 --session ...
2026-06-26 02:01:20 | DEBUG    | importer     | [42/142] Creating: Google
```

---

## Limitations

- **One-way only** — Vaultwarden to Bitwarden. Changes made directly in Bitwarden are overwritten on the next sync.
- **Full replace** — Each sync deletes all items from the Bitwarden vault and re-imports them. There is no incremental or delta sync.
- **No file attachments** — Attached files are not synced. This is planned for a future release.
- **Single user** — Syncs one personal vault. Organization and multi-user support are on the roadmap.
- **No real-time sync** — Runs on a schedule, not triggered by vault changes.

---

## Troubleshooting

### Sync fails with "Bitwarden CLI command failed (login)"

- Verify `VAULTWARDEN_URL` is reachable from the container
- Check that `VAULTWARDEN_CLIENT_ID` and `VAULTWARDEN_CLIENT_SECRET` are correct
- Ensure your Vaultwarden instance supports API keys (v1.30+)
- Try email and password authentication as a fallback

### Sync fails with "Bitwarden CLI command failed (unlock)"

- Verify `VAULTWARDEN_MP` is correct
- If using API key authentication, ensure your Vaultwarden version supports API key unlock
- Check for special characters in the password that may need escaping in `.env`

### "Failed to create item" or rate limit errors

- Reduce `IMPORT_WORKERS` — the default is 5, try 2
- Bitwarden cloud enforces rate limits — the sync retries automatically with exponential backoff
- If the issue persists, schedule your sync during off-peak hours

### Enable debug logging

```env
LOG_LEVEL=DEBUG
```

Then view the logs:

```bash
docker compose logs -f mitchvault-sync
```

Debug mode shows every Bitwarden CLI command, every API response, and per-item progress.

### Sync reports "0 items exported"

- Your Vaultwarden vault may be empty, or
- The Bitwarden CLI session may have expired — check the container logs for authentication errors
- Verify your Vaultwarden user has items in their personal vault (not only in an organization)

### Container shows "unhealthy"

- The healthcheck verifies that `/data/last_sync` exists
- This file is created after the first successful sync completes
- If the initial sync fails, the container stays unhealthy until a sync succeeds
- Check the logs to diagnose why the initial sync failed

---

## Building for ARM

The Dockerfile detects your architecture automatically. For ARM devices (Raspberry Pi, Apple Silicon):

```bash
docker compose build --build-arg BW_VERSION=2024.11.1
```

The Bitwarden CLI binary is downloaded for the correct architecture at build time.

---

## Security

- **API keys** and **master passwords** are stored as environment variables in your `.env` file
- Use Docker secrets or a secrets manager for production deployments
- Never commit `.env` to version control (it is listed in `.gitignore`)
- The vault cache file (`/data/vault_cache.json`) contains **decrypted** vault items — mount the data volume on encrypted storage if your threat model requires it
- The Bitwarden CLI session data is stored in `/data/vaultwarden/` and `/data/bitwarden/` — these directories persist across container restarts

See **[PRIVACY.md](PRIVACY.md)** for a comprehensive document covering data flow, encryption states, storage locations, and hardening recommendations.

To report a vulnerability, see **[SECURITY.md](SECURITY.md)**.

---

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for code style requirements — human-readable names and messages are mandatory — plus commit conventions and pull request workflow.

---

## License

[GNU General Public License v3.0](LICENSE)

```
MitchVault Sync — One-way Vaultwarden to Bitwarden vault synchronization.
Copyright (C) 2026  MitchVault Sync Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
```

---

<div align="center">

**[Documentation](README.md)** &nbsp;|&nbsp;
**[Privacy & Security](PRIVACY.md)** &nbsp;|&nbsp;
**[Contributing](CONTRIBUTING.md)** &nbsp;|&nbsp;
**[Report a Bug](https://github.com/mitchelljfranklin/mitchvault-sync/issues/new?template=bug_report.yml)** &nbsp;|&nbsp;
**[Request a Feature](https://github.com/mitchelljfranklin/mitchvault-sync/issues/new?template=feature_request.yml)**

Made with :heart: for the self-hosting community.

</div>
