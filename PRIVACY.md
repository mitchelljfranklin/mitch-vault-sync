# Privacy & Security

This document covers what data MitchVault Sync handles, where it flows, how it's stored, and how to harden your deployment.

## Data Flow

```
┌─────────────────┐          ┌──────────────────┐          ┌─────────────────┐
│   Vaultwarden   │   TLS    │  MitchVault Sync  │   TLS    │  Bitwarden Cloud │
│    (local)      │◄────────►│    (container)     │◄────────►│   (api.bitwarden.com│
└─────────────────┘          └──────┬───────────┘          └─────────────────┘
                                     │
                                     ▼
                             /data/vault_export.json
                        (decrypted vault — deleted after each cycle)
```

## What Data the Container Handles

| Data | Source | Format In Transit | Format At Rest |
|---|---|---|---|
| Vault items (logins, passkeys, notes, cards, identities) | Vaultwarden | TLS-encrypted | **Decrypted** in `/data/vault_export.json` during the sync cycle only |
| Master password | `.env` file | Not transmitted over network | Plain text in environment variable |
| API keys (client id + secret) | `.env` file | TLS-encrypted (Bearer token) | Plain text in environment variable |
| `bw` CLI session tokens | Generated at runtime | N/A (local only) | In-memory only |
| Sync timestamps | Generated at runtime | N/A | `/data/last_sync` (ISO-8601 string) |

## Storage Locations

### `/data/vault_export.json`

**Contains your fully decrypted vault** — every password, passkey credential, TOTP seed, note, and custom field in plain JSON. This file is:

- Created by a single `bw export` call during the export phase
- Consumed by a single `bw import` call during the import phase
- **Deleted at the end of every sync cycle**, successful or not

It does not persist between cycles.

**Mitigation**: The file is only needed during active sync. If your storage is encrypted at the filesystem level (LUKS, dm-crypt), the plaintext is protected at rest. You can mount the `./data` volume on a `tmpfs` to keep it in memory only:

```yaml
volumes:
  - type: tmpfs
    target: /data
```

Tradeoff: `bw` CLI state (account tokens) is also stored in `/data`, so using tmpfs means re-authenticating on every container restart.

### `/data/vaultwarden/` and `/data/bitwarden/`

Bitwarden CLI state directories. Contain:

- Server URL configuration
- Encrypted master key material
- Temporary API session data

**These do NOT contain your master password or decrypted vault items.** The `bw` CLI stores credentials encrypted with your master key.

### `.env` file

Contains your API keys and master password in plain text. This file:

- Is excluded from version control (`.gitignore`)
- Should be readable only by root (`chmod 600 .env`)
- Should never be committed, shared, or backed up without encryption

## Encryption States

| Stage | Encryption |
|---|---|
| Vaultwarden → Container (export) | TLS (HTTPS) |
| Inside container during export | Decrypted (in memory + export file) |
| Container → Bitwarden Cloud (import) | TLS (HTTPS) |
| Bitwarden Cloud at rest | Encrypted with your Bitwarden master key |

The container acts as a **decryption/encryption relay**. It decrypts items from Vaultwarden, then re-encrypts them for Bitwarden. During this gap, items exist in plaintext within the container's memory and the transient export file.

## Security Recommendations

### Required

| Practice | Reason |
|---|---|
| Never commit `.env` to version control | Contains master password and API keys |
| Use API keys instead of passwords where possible | API keys can be scoped and revoked independently |
| Run the container on a trusted host | Export file contains your entire vault in plaintext while a sync runs |

### Recommended

| Practice | How |
|---|---|
| Encrypt the host filesystem | LUKS on Linux, FileVault on macOS |
| Restrict `.env` permissions | `chmod 600 .env` |
| Use Docker secrets | `docker secret create` instead of env vars in Swarm mode |
| Mount data volume as tmpfs | Keeps the export file in RAM, never written to disk |
| Use a dedicated Bitwarden account | Create a separate Bitwarden account just for the backup, limiting blast radius |
| Rotate API keys periodically | Bitwarden: revoke and reissue; Vaultwarden: similar in web UI |
| Monitor container logs | Watch for auth failures, which could indicate credential compromise |

### Production Hardening

For deployments where the host is shared or security posture is high, `docker-compose.yml` ships with a hardening block ready to uncomment: non-root user, read-only root filesystem, dropped capabilities, and `no-new-privileges`. Uncomment the "Optional hardening" section there — the only preparation needed is owning the data directory with the matching uid:

```bash
chown -R 1000:1000 ./data
```

To also keep the transient plaintext export out of disk entirely, swap the volumes block for the documented tmpfs alternative (tradeoff: re-authentication on every restart).

## Data Minimization

MitchVault Sync processes the minimum data needed to function:

- **No telemetry** — the container makes zero outbound calls except to your Vaultwarden instance and Bitwarden's API
- **No analytics** — no third-party services, no usage tracking, no crash reporting
- **No external logging** — logs go to stdout/stderr only (Docker's logging driver)
- **No data retention beyond your control** — all data stays on your host until the next sync overwrites it

## Vulnerability Reporting

If you discover a security vulnerability, please follow the process in **[SECURITY.md](SECURITY.md)**. Do not open a public issue.

## External Dependencies

| Dependency | Purpose | Data Accessed |
|---|---|---|
| `bw` CLI (Bitwarden/clients) | Export from Vaultwarden, import to Bitwarden | Full vault contents |
| `APScheduler` (Python) | Schedule management | None |
| `python:3.12-slim` (Docker Hub) | Base image | None |

The `bw` CLI binary is downloaded directly from [GitHub Releases](https://github.com/bitwarden/clients/releases) during the Docker build. The Python dependencies are installed from PyPI.

## Questions

For questions about privacy or security, open a [GitHub Discussion](https://github.com/mitchelljfranklin/mitchvault-sync/discussions) instead of an issue.
