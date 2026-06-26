# Security Policy

This document outlines the security policy for MitchVault Sync — how to report vulnerabilities, which versions receive updates, and what to expect from the maintainers.

For a deeper analysis of data flow, encryption states, and hardening guidance, see **[PRIVACY.md](PRIVACY.md)**.

## Supported Versions

Only the latest commit on the `main` branch receives security patches. There are no formal releases yet.

| Version | Supported |
|---|---|
| `main` (latest commit) | :white_check_mark: |
| Any prior commit | :x: |

When tagged releases are introduced, this table will be updated with a support window for each major version.

## Reporting a Vulnerability

MitchVault Sync handles your entire password vault. If you discover a security vulnerability, please report it responsibly.

### How to Report

**Do not open a public issue.** Instead, send a detailed report to the repository maintainers via one of these channels:

1. **GitHub Security Advisory** — Use the [private vulnerability reporting](https://github.com/mitchelljfranklin/mitchvault-sync/security/advisories/new) feature on the repository. This is the preferred channel.
2. **Direct message** — Contact the maintainer directly through GitHub if the advisory feature is unavailable.

### What to Include

A good report helps us reproduce and fix the issue quickly. Please include:

- A clear description of the vulnerability and its potential impact
- Steps to reproduce the issue, including any specific configuration or environment details
- The affected component (export phase, import phase, scheduler, Dockerfile, dependency)
- If available, a proof of concept or suggested fix
- Whether you believe the vulnerability is publicly known or has been exploited

### What to Expect

| Timeframe | Action |
|---|---|
| Within 48 hours | You will receive an acknowledgment of your report |
| Within 7 days | We will confirm the vulnerability and assess its severity |
| Within 30 days | We aim to release a fix for confirmed vulnerabilities |
| Ongoing | You will be kept informed of progress at each stage |

If a vulnerability is declined, you will receive an explanation. If accepted, we will coordinate a disclosure date with you.

## Disclosure Process

1. The reporter submits a vulnerability privately
2. The maintainer acknowledges receipt within 48 hours
3. The maintainer validates and assesses severity
4. A fix is developed and tested
5. A security advisory is published on GitHub with credit to the reporter
6. The fix is merged to `main`

Public disclosure happens **after** the fix is merged. We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure) practices.

## Scope

The following are in scope for security reports:

- The sync orchestration code (`sync.py`, `src/`)
- The Docker image and build process (`Dockerfile`, `docker-compose.yml`)
- How credentials and vault data are handled during sync
- Dependencies that could introduce vulnerabilities
- Documentation that could lead to insecure configurations

### Out of Scope

- Issues in your Vaultwarden instance or Bitwarden cloud account (report those to the respective projects)
- Vulnerabilities that require physical access to the host machine
- Social engineering or phishing attacks
- Denial of service against the container (it runs on your own infrastructure)
- Issues in third-party dependencies that have already been publicly disclosed with available fixes

## Supply Chain

MitchVault Sync depends on the following external components. We monitor their security advisories and update pinned versions promptly.

| Dependency | Source | Verification |
|---|---|---|
| Bitwarden CLI (`bw`) | [GitHub Releases](https://github.com/bitwarden/clients/releases) | Downloaded via HTTPS during Docker build |
| `python:3.12-slim` | Docker Hub | Official Python image |
| `APScheduler` | PyPI | Pinned version range in `requirements.txt` |

The `bw` CLI binary version is configurable at build time via the `BW_VERSION` argument in the Dockerfile.

## Security Design

Key security properties of MitchVault Sync:

- **No network listeners** — the container does not expose any ports or accept incoming connections
- **No telemetry** — zero outbound calls except to your Vaultwarden instance and Bitwarden's API
- **TLS everywhere** — all external communication is over HTTPS
- **Credential isolation** — Vaultwarden and Bitwarden sessions use separate `BW_DATA_DIR` directories
- **API key preference** — API keys are preferred over passwords because they can be scoped and revoked independently

See **[PRIVACY.md](PRIVACY.md)** for a complete data flow diagram, encryption state table, and Docker hardening example (non-root, read-only filesystem, dropped capabilities).

## Past Advisories

None as of the current release. Published advisories will appear on the [Security Advisories](https://github.com/mitchelljfranklin/mitchvault-sync/security/advisories) page.

## Acknowledgments

We thank everyone who reports vulnerabilities responsibly. With your permission, reporters will be credited in the published advisory.

---

For questions that are not security-sensitive, use [GitHub Discussions](https://github.com/mitchelljfranklin/mitchvault-sync/discussions).
