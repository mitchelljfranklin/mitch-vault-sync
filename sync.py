#!/usr/bin/env python3
"""MitchVault Sync — One-way Vaultwarden to Bitwarden vault synchronization."""

import os
import sys
import signal
import time
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from src.logger import setup_logging, get_logger
from src.exporter import VaultwardenExporter
from src.importer import BitwardenImporter

logger = get_logger("mitchvault")

_sync_lock = threading.Lock()


def parse_schedule():
    cron = os.getenv("SYNC_CRON", "").strip()
    schedule = os.getenv("SYNC_SCHEDULE", "daily").strip().lower()

    if cron:
        logger.info("Schedule: %s (cron)", cron)
        return CronTrigger.from_crontab(cron, timezone="UTC")

    simple = {
        "hourly": ("hours", 1),
        "daily": ("hours", 24),
        "24h": ("hours", 24),
        "12h": ("hours", 12),
        "6h": ("hours", 6),
        "4h": ("hours", 4),
        "2h": ("hours", 2),
        "1h": ("hours", 1),
        "weekly": ("weeks", 1),
        "7d": ("days", 7),
    }

    if schedule in simple:
        unit, val = simple[schedule]
        logger.info("Schedule: every %d %s", val, unit)
        return IntervalTrigger(**{unit: val})

    try:
        parts = schedule.split()
        hour, minute = map(int, parts[0].split(":"))
        tz = parts[1] if len(parts) > 1 else "UTC"
        logger.info("Schedule: daily at %02d:%02d %s", hour, minute, tz)
        return CronTrigger(hour=hour, minute=minute, timezone=tz)
    except (ValueError, IndexError):
        pass

    logger.warning(
        "Unrecognized schedule '%s', defaulting to daily",
        os.getenv("SYNC_SCHEDULE"),
    )
    return IntervalTrigger(hours=24)


def validate_env():
    required = {
        "VAULTWARDEN_URL": "Vaultwarden server URL",
        "VAULTWARDEN_MP": "Vaultwarden master password",
        "BITWARDEN_CLIENT_ID": "Bitwarden API key client ID",
        "BITWARDEN_CLIENT_SECRET": "Bitwarden API key client secret",
    }

    missing = [f"{k} ({v})" for k, v in required.items() if not os.getenv(k)]
    if missing:
        logger.error("Missing required environment variables:")
        for m in missing:
            logger.error("  - %s", m)
        return False

    has_api_key = bool(
        os.getenv("VAULTWARDEN_CLIENT_ID")
        and os.getenv("VAULTWARDEN_CLIENT_SECRET")
    )
    has_email = bool(
        os.getenv("VAULTWARDEN_EMAIL")
        and os.getenv("VAULTWARDEN_PASSWORD")
    )

    if not has_api_key and not has_email:
        logger.error(
            "Vaultwarden auth: set VAULTWARDEN_CLIENT_ID/SECRET "
            "or VAULTWARDEN_EMAIL/PASSWORD"
        )
        return False

    return True


def run_sync():
    if not _sync_lock.acquire(blocking=False):
        logger.warning("Sync already in progress, skipping this cycle")
        return False

    try:
        start = time.time()
        logger.info("=" * 60)
        logger.info("MitchVault Sync — starting cycle")
        logger.info("=" * 60)

        exporter = VaultwardenExporter()
        cache = exporter.run()

        importer = BitwardenImporter()
        result = importer.run(cache)

        elapsed = time.time() - start
        logger.info(
            "Sync complete: exported %d, imported %d in %.0fs",
            result["exported"],
            result["imported"],
            elapsed,
        )

        with open("/data/last_sync", "w") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        return True

    except Exception as e:
        elapsed = time.time() - start
        logger.error("Sync FAILED after %.0fs: %s", elapsed, e, exc_info=True)
        return False

    finally:
        _sync_lock.release()


def main():
    setup_logging()
    logger.info("MitchVault Sync starting")

    if not validate_env():
        sys.exit(1)

    trigger = parse_schedule()

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_sync,
        trigger=trigger,
        id="mitchvault-sync",
        name="MitchVault Sync Job",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Running initial sync on startup...")
    run_sync()

    def shutdown(signum, frame):
        logger.info("Received signal %d, shutting down...", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        pass

    scheduler.shutdown(wait=False)
    logger.info("MitchVault Sync stopped")


if __name__ == "__main__":
    main()
