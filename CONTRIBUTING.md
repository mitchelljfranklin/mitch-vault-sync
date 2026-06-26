# Contributing to MitchVault Sync

Thank you for contributing. This document covers what we expect from contributions — code style, commit messages, and pull request workflow.

## Quick Checklist

Before submitting a pull request, make sure:

- [ ] Variable names are fully spelled out (no `mp`, `ex`, `fut`, `idx`, `tz`)
- [ ] Log and error messages are plain English sentences (see [Human-Readable Code](#human-readable-code))
- [ ] Commit messages follow the [Commit Style](#commit-style) format
- [ ] Python syntax is valid: `python3 -m py_compile sync.py src/*.py`
- [ ] Existing behavior is not broken if you cannot test it

## Human-Readable Code

This is a hard requirement. Every variable name, log message, and error message must be understandable to someone reading the code for the first time.

### Variable Names

No abbreviations, no single letters, no shorthand.

| Avoid | Use |
|---|---|
| `mp`, `mk`, `pw` | `master_password` |
| `ex` | `executor` |
| `fut` | `future` |
| `idx`, `i` | `item_index`, `index` |
| `tz` | `schedule_timezone` |
| `k`, `v` | `variable_name`, `variable_description` |
| `cmd` | `command` |
| `env` (parameter) | `extra_environment` |
| `stdin` (parameter) | `standard_input` |
| `proc_env` | `process_environment` |
| `f` (file handle) | `cache_file`, `sync_timestamp_file` |
| `p` (path) | `candidate_path` |
| `raw` | `raw_output` |
| `old_fid` | `old_folder_id` |
| `cred` | `credential` |
| `err` | `error_message` |
| `signum` | `signal_number` |
| `fmt`, `datefmt` | `log_format`, `date_format` |
| `e` (exception) | `error` |

The only exceptions are:

- `*args` / `**kwargs` in function signatures (Python convention)
- `_` for unused variables (Python convention, e.g. `_frame` in signal handlers)
- `id` as a key name when it comes from external APIs (e.g., `item["id"]`)
- Environment variable names that external tools expect verbatim (e.g., `BW_CLIENTID`, `BW_DATA_DIR`)

### Log and Error Messages

Every message must form a complete, grammatical English sentence. The reader should never need to consult the code to understand what happened.

| Avoid | Use |
|---|---|
| `bw: login --apikey` | `Bitwarden CLI: login --apikey` |
| `bw login failed` | `Bitwarden CLI command failed (login): <reason>` |
| `Cache: 142 items` | `Loaded cache: 142 items, 6 folders` |
| `Rate limited, waiting 4s (1/3)` | `Rate limited by server, waiting 4 seconds (attempt 1 of 3)` |
| `Sync FAILED after 50s` | `Sync failed after 50 seconds: <error details>` |
| `Conf server` | `Configuring Vaultwarden server: https://...` |
| `Deleting items...` | `Deleting 12 existing items...` |

Rules for messages:

1. Start with a capital letter
2. Include relevant context (counts, IDs, durations)
3. Include units in words, not symbols (`seconds`, not `s`)
4. Include the cause in error messages (use `exc_info=True` for stack traces)
5. Avoid internal jargon or acronyms the user may not know
6. Use full words for file/command names (`Bitwarden CLI`, not `bw`)

### Comments

Comments are allowed but not required. If you add a comment, it must explain **why**, not **what**. The code should already be readable enough to convey what is happening.

```python
# Avoid — the code already says this
# Delete items
for item in items:
    ...

# Acceptable — explains a non-obvious reason
# Remap folder IDs because Bitwarden assigns new IDs on the target server
clean["folderId"] = folder_map[old_folder_id]
```

## Commit Style

Write commit messages in the imperative mood as if giving a command:

```
Summarise the change in 50-72 characters

Explain what was done and why. Reference any relevant issue numbers.
Keep lines wrapped at 72 characters.
```

Good examples:

```
Fix human-readable renames in exporter error messages
```

```
Add CONTRIBUTING.md with code style and review guidelines
```

```
Rename mp → master_password across all source files
```

Avoid vague messages like `fix`, `update`, `wip`, `changes`.

## Pull Request Workflow

1. Fork the repository
2. Create a branch from `main`: `git checkout -b your-description`
3. Make your changes, following the [Human-Readable Code](#human-readable-code) rules
4. Verify Python syntax: `python3 -m py_compile sync.py src/*.py`
5. Write clear commit messages following the [Commit Style](#commit-style)
6. Push your branch and open a pull request against `main`
7. In the PR description:
   - Summarise what you changed
   - Explain why the change is needed
   - Note any limitations or follow-up work needed
   - If the PR affects logging, include sample log output showing before and after

## Code Review

All submissions require review. A maintainer will check for:

1. **Human readability** — variable names, log messages, error messages (this is the top priority)
2. **Correctness** — does the change do what it claims without breaking existing behaviour
3. **Consistency** — does it follow the patterns already established in the codebase
4. **Security** — no secrets logged, no plaintext credentials written to disk unnecessarily
5. **Error handling** — are edge cases handled, are exceptions caught with clear messages

Pull requests that use abbreviated variable names or terse log messages will be asked to revise before review proceeds.

## Testing

There is no automated test suite yet. When testing your changes manually:

1. Set `LOG_LEVEL=DEBUG` in your `.env` file
2. Run the container: `docker compose up --build`
3. Check the logs: `docker compose logs -f`
4. Verify that sync completes and item counts match
5. Open Bitwarden and spot-check that items, folders, passkeys, and TOTP seeds transferred correctly

If you add a new feature, please describe how you tested it in the PR description.

## Reporting Issues

- **Bug reports** — use the bug report template (`.github/ISSUE_TEMPLATE/bug_report.yml`)
- **Feature requests** — use the feature request template (`.github/ISSUE_TEMPLATE/feature_request.yml`)
- **Setup help** — use the configuration help template (`.github/ISSUE_TEMPLATE/config_help.yml`)
- **Security vulnerabilities** — do NOT open a public issue. See [PRIVACY.md](PRIVACY.md#vulnerability-reporting)

## Questions

For questions about contributing that are not covered here, open a [GitHub Discussion](https://github.com/mitchelljfranklin/mitchvault-sync/discussions).
