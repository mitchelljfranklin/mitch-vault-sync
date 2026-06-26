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
    cron_expression = os.getenv("SYNC_CRON", "").strip()
    schedule_config = os.getenv("SYNC_SCHEDULE", "daily").strip().lower()

    if cron_expression:
        logger.info("Schedule: %s (cron)", cron_expression)
        return CronTrigger.from_crontab(cron_expression, timezone="UTC")

    simple_schedules = {
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

    if schedule_config in simple_schedules:
        interval_unit, interval_value = simple_schedules[schedule_config]
        logger.info("Schedule: every %d %s", interval_value, interval_unit)
        return IntervalTrigger(**{interval_unit: interval_value})

    try:
        schedule_parts = schedule_config.split()
        hour, minute = map(int, schedule_parts[0].split(":"))
        schedule_timezone = schedule_parts[1] if len(schedule_parts) > 1 else "UTC"
        logger.info("Schedule: daily at %02d:%02d %s", hour, minute, schedule_timezone)
        return CronTrigger(hour=hour, minute=minute, timezone=schedule_timezone)
    except (ValueError, IndexError):
        pass

    logger.warning(
        "Unrecognized schedule '%s', defaulting to daily",
        os.getenv("SYNC_SCHEDULE"),
    )
    return IntervalTrigger(hours=24)


def validate_env():
    required_variables = {
        "VAULTWARDEN_URL": "Vaultwarden server URL",
        "VAULTWARDEN_MP": "Vaultwarden master password",
        "BITWARDEN_CLIENT_ID": "Bitwarden API key client ID",
        "BITWARDEN_CLIENT_SECRET": "Bitwarden API key client secret",
    }

    missing_variables = [
        f"{variable_name} ({variable_description})"
        for variable_name, variable_description in required_variables.items()
        if not os.getenv(variable_name)
    ]
    if missing_variables:
        logger.error("Missing required environment variables:")
        for missing_entry in missing_variables:
            logger.error("  - %s", missing_entry)
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
        start_time = time.time()
        logger.info("=" * 60)
        logger.info("MitchVault Sync — starting cycle")
        logger.info("=" * 60)

        exporter = VaultwardenExporter()
        cache = exporter.run()

        importer = BitwardenImporter()
        result = importer.run(cache)

        elapsed = time.time() - start_time
        logger.info(
            "Sync complete: exported %d, imported %d in %.0fs",
            result["exported"],
            result["imported"],
            elapsed,
        )

        with open("/data/last_sync", "w") as sync_timestamp_file:
            sync_timestamp_file.write(
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            )

        return True

    except Exception as error:
        elapsed = time.time() - start_time
        logger.error("Sync FAILED after %.0fs: %s", elapsed, error, exc_info=True)
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

    def shutdown(signal_number, _frame):
        logger.info("Received signal %d, shutting down...", signal_number)
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
