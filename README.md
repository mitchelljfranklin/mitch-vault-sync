# Mitch Vault Sync

<div align="center">

![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-ready-brightgreen)
![Platform](https://img.shields.io/badge/platform-linux%2Farm-lightgrey)
[![PRs Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen)](CONTRIBUTING.md)

</div>

> Your Vaultwarden vault. Backed up to Bitwarden. Every day. Automatically.

Keep your self-hosted passwords safe in the cloud. MitchVault Sync mirrors your local [Vaultwarden](https://github.com/dani-garcia/vaultwarden) vault to [Bitwarden](https://bitwarden.com) cloud — no manual exports, no missed items, passkeys included.

```
                         MitchVault Sync
┌──────────────────┐     ┌─────────────────────────┐     ┌──────────────────┐
│   Vaultwarden    │────▶│  ┌─────────┐ ┌────────┐  │────▶│  Bitwarden Cloud │
│    (your LAN)    │     │  │ export  │ │ import │  │     │    (backup)      │
│                  │     │  │ 1 call  │ │ 1 call │  │     │                  │
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
| :mag: Visibility | INFO logs for overview, DEBUG for every CLI command |
| :lock: Security | API key auth for the target, TLS everywhere, no telemetry, no third parties |
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
2. Use your account **email** and **password** to authenticate

Vaultwarden does not support personal API keys. Use `VAULTWARDEN_EMAIL` and `VAULTWARDEN_PASSWORD` in your `.env` file.

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# ── Vaultwarden (source) ──────────────────────────────────
VAULTWARDEN_URL=https://vault.example.com
VAULTWARDEN_MP=your-master-password

# Auth: email/password
VAULTWARDEN_EMAIL=user@example.com
VAULTWARDEN_PASSWORD=your-password

# ── Bitwarden Cloud (target) ──────────────────────────────
BITWARDEN_CLIENT_ID=user.your-client-id
BITWARDEN_CLIENT_SECRET=your-client-secret
BITWARDEN_SERVER=https://vault.bitwarden.com       # or vault.bitwarden.eu
BITWARDEN_MP=your-master-password

# ── Scheduling ────────────────────────────────────────────
SYNC_SCHEDULE=daily       # hourly | daily | 12h | 6h | weekly | 7d | "3:00"

# ── Logging ───────────────────────────────────────────────
LOG_LEVEL=INFO            # DEBUG for troubleshooting
```

<details>
<summary><b>Full Environment Variable Reference</b> (click to expand)</summary>

| Variable | Required | Default | Description |
|---|---|---|---|---|
| `VAULTWARDEN_URL` | Yes | — | Your Vaultwarden instance URL |
| `VAULTWARDEN_MP` | Yes | — | Master password to unlock the Vaultwarden vault |
| `VAULTWARDEN_EMAIL` | Yes | — | Email address for Vaultwarden login |
| `VAULTWARDEN_PASSWORD` | Yes | — | Password for Vaultwarden login |
| `BITWARDEN_CLIENT_ID` | Yes | — | Bitwarden cloud API key client ID |
| `BITWARDEN_CLIENT_SECRET` | Yes | — | Bitwarden cloud API key client secret |
| `BITWARDEN_SERVER` | No | `https://vault.bitwarden.com` | Bitwarden server — use `.eu` for EU region |
| `BITWARDEN_MP` | Yes | — | Master password to unlock the Bitwarden vault |
| `SYNC_SCHEDULE` | No | `daily` | Human-readable schedule (see [Scheduling](#scheduling)) |
| `SYNC_CRON` | No | — | Raw cron expression — overrides `SYNC_SCHEDULE` |
| `LOG_LEVEL` | No | `INFO` | Log verbosity — `INFO` or `DEBUG` |
| `HEALTHCHECK_MAX_AGE_HOURS` | No | `48` | Hours after which a stale last sync marks the container unhealthy |

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

The container reports **healthy** only while `/data/last_sync` is fresh — written after each successful sync and checked against `HEALTHCHECK_MAX_AGE_HOURS` (default 48). If syncs start failing, the container turns unhealthy once the last success ages past that window, so a broken backup never looks fine.

### Architecture

```
mitchvault-sync/
├── sync.py                 # Entrypoint — scheduler and orchestrator
├── src/
│   ├── bw_cli.py           # Shared Bitwarden CLI runner (session-key redaction)
│   ├── exporter.py         # Phase 1: Single-call vault export from Vaultwarden
│   └── importer.py         # Phase 2: Clear + single-call import to Bitwarden cloud
├── data/                   # Mounted volume — CLI state and transient export
│   ├── vaultwarden/        # Bitwarden CLI data directory (isolated session)
│   ├── bitwarden/          # Bitwarden CLI data directory (isolated session)
│   ├── vault_export.json   # Plaintext export, deleted at the end of every cycle
│   └── last_sync           # Timestamp of last successful sync
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── .env                    # Your configuration (never committed)
```

### Sync Flow

1. **Login** — Authenticate to Vaultwarden with email/password via the Bitwarden CLI
2. **Unlock** — Decrypt the source vault with your master password
3. **Export** — One `bw export` call writes the fully decrypted vault to `/data/vault_export.json`
4. **Login** — Authenticate to Bitwarden cloud via the Bitwarden CLI (API key)
5. **Unlock** — Decrypt the target vault with your Bitwarden master password
6. **Clear** — Permanently delete all existing items and folders from the Bitwarden vault
7. **Import** — One `bw import` call loads the entire exported vault, rebuilding folders natively
8. **Verify** — Compare item counts, delete the export file, write a success timestamp

### Performance

Sync time is dominated by the clear phase (one API call per existing item). The export and import themselves are single calls each, so total time scales far better than item-by-item approaches:

| Vault Size | Total Time |
|---|---|
| 50 items | ~20 seconds |
| 200 items | ~45 seconds |
| 500 items | ~90 seconds |
| 1000 items | ~3 minutes |

Times are approximate and depend on network latency.

> **Tip**
> If a sync cycle fails partway, the container healthcheck turns unhealthy within `HEALTHCHECK_MAX_AGE_HOURS` — check the logs for the failing step.

---

## Logging

Default log level is `INFO`. You will see phase transitions, item counts, and a final summary:

```
2026-06-26 02:00:01 | INFO     | mitchvault   | MitchVault Sync — starting cycle
2026-06-26 02:00:09 | INFO     | exporter     | Export complete: 142 items, 6 folders
2026-06-26 02:00:15 | INFO     | importer     | Importing 142 items via Bitwarden CLI import...
2026-06-26 02:00:21 | INFO     | importer     | Import verified: 142/142 items present in Bitwarden
2026-06-26 02:00:22 | INFO     | mitchvault   | Sync complete: exported 142, imported 142 in 21s
```

Set `LOG_LEVEL=DEBUG` for every Bitwarden CLI command (session keys are always masked):

```
2026-06-26 02:00:05 | DEBUG    | exporter     | Bitwarden CLI: export --format json --output /data/vault_export.json --session ***session***
2026-06-26 02:00:09 | INFO     | exporter     | Export complete: 142 items, 6 folders
2026-06-26 02:00:15 | INFO     | importer     | Importing 142 items via Bitwarden CLI import...
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
- Check that `VAULTWARDEN_EMAIL` and `VAULTWARDEN_PASSWORD` are correct

### Sync fails with "Bitwarden CLI command failed (unlock)"

- Verify `BITWARDEN_MP` is correct (API keys are for login only, vault decryption always requires the master password)
- Check for special characters in the password that may need escaping in `.env`

### "Import verification failed" or import errors

- The importer compares item counts before declaring success — a mismatch means the native import did not complete; check the preceding CLI error
- Bitwarden cloud enforces rate limits — the sync is a single bulk call, so re-run the cycle after waiting a few minutes
- Confirm the target vault has no folder/collection policies blocking personal items

### Enable debug logging

```env
LOG_LEVEL=DEBUG
```

Then view the logs:

```bash
docker compose logs -f mitchvault-sync
```

Debug mode shows every Bitwarden CLI command (session keys masked) and per-phase progress.

### Sync reports "0 items exported"

- Your Vaultwarden vault may be empty, or
- The Bitwarden CLI session may have expired — check the container logs for authentication errors
- Verify your Vaultwarden user has items in their personal vault (not only in an organization)

### Container shows "unhealthy"

- The healthcheck fails when `/data/last_sync` is missing **or older than** `HEALTHCHECK_MAX_AGE_HOURS` (default 48)
- A stale timestamp means recent syncs have been failing even if the container itself is running
- Check the logs to diagnose why the current sync failed

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
- The export file (`/data/vault_export.json`) contains **decrypted** vault items while a sync runs — it is deleted at the end of every cycle; mount the data volume on encrypted storage or tmpfs if your threat model requires it
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
