import os
import json
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .logger import get_logger

logger = get_logger(__name__)


class VaultwardenExporter:
    def __init__(self, data_dir="/data/vaultwarden", cache_path="/data/vault_cache.json"):
        self.data_dir = data_dir
        self.cache_path = cache_path
        self.url = os.getenv("VAULTWARDEN_URL", "").rstrip("/")
        self.master_password = os.getenv("VAULTWARDEN_MP", "")
        self.client_id = os.getenv("VAULTWARDEN_CLIENT_ID")
        self.client_secret = os.getenv("VAULTWARDEN_CLIENT_SECRET")
        self.email = os.getenv("VAULTWARDEN_EMAIL")
        self.password = os.getenv("VAULTWARDEN_PASSWORD")
        self.max_workers = int(os.getenv("EXPORT_WORKERS", "10"))

    def _bw_path(self):
        for candidate_path in ["bw", "/usr/local/bin/bw"]:
            if shutil.which(candidate_path):
                return candidate_path
        return "bw"

    def _run(self, *arguments, extra_environment=None, standard_input=None, timeout=120):
        command = [self._bw_path(), *arguments]
        logger.debug("bw: %s", " ".join(str(a) for a in arguments))

        process_environment = os.environ.copy()
        process_environment["BW_DATA_DIR"] = self.data_dir
        if extra_environment:
            process_environment.update(extra_environment)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=process_environment,
            timeout=timeout,
            input=standard_input,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"bw {' '.join(arguments)} failed: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def run(self):
        os.makedirs(self.data_dir, exist_ok=True)

        session = None
        try:
            # 1. Configure server
            logger.info("Configuring Vaultwarden server: %s", self.url)
            self._run("config", "server", self.url)

            # 2. Login
            logger.info("Logging into Vaultwarden...")
            if self.client_id and self.client_secret:
                logger.debug("Using API key auth")
                self._run(
                    "login",
                    "--apikey",
                    extra_environment={
                        "BW_CLIENTID": self.client_id,
                        "BW_CLIENTSECRET": self.client_secret,
                    },
                )
            elif self.email and self.password:
                logger.debug("Using email/password auth")
                self._run(
                    "login",
                    self.email,
                    "--passwordenv",
                    "BW_PASSWORD",
                    extra_environment={"BW_PASSWORD": self.password},
                )
            else:
                raise RuntimeError(
                    "Set VAULTWARDEN_CLIENT_ID/SECRET or VAULTWARDEN_EMAIL/PASSWORD"
                )

            # 3. Unlock
            logger.debug("Unlocking vault...")
            session = self._unlock()

            # 4. List items
            logger.info("Listing vault items...")
            items_raw_output = self._run("list", "items", "--session", session)
            items = json.loads(items_raw_output)
            logger.info("Found %d items", len(items))

            if not items:
                logger.warning("No items found in vault")
                cache = {
                    "items": [],
                    "folders": [],
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                }
                with open(self.cache_path, "w") as cache_file:
                    json.dump(cache, cache_file)
                return cache

            # 5. Fetch full items in parallel
            logger.info(
                "Fetching %d items (%d workers)...",
                len(items),
                self.max_workers,
            )
            full_items = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._get_item, item_summary["id"], session): item_summary
                    for item_summary in items
                }
                for index, future in enumerate(as_completed(futures), 1):
                    item = future.result()
                    full_items.append(item)
                    logger.debug(
                        "[%d/%d] %s", index, len(items), item.get("name", "Unknown")
                    )

            # 6. Get folders
            logger.debug("Fetching folders...")
            folders_raw_output = self._run("list", "folders", "--session", session)
            folders = json.loads(folders_raw_output)
            logger.info("Found %d folders", len(folders))

            # 7. Save cache
            cache = {
                "items": full_items,
                "folders": folders,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.cache_path, "w") as cache_file:
                json.dump(cache, cache_file, indent=2, default=str)

            logger.info(
                "Exported %d items, %d folders -> %s",
                len(full_items),
                len(folders),
                self.cache_path,
            )
            return cache

        finally:
            # Always logout
            try:
                self._run("logout")
            except Exception:
                pass

    def _unlock(self):
        try:
            return self._run("unlock", "--apikey", "--raw")
        except RuntimeError:
            logger.debug("API key unlock failed, trying master password...")
            return self._run(
                "unlock",
                "--passwordenv",
                "BW_PASSWORD",
                "--raw",
                extra_environment={"BW_PASSWORD": self.master_password},
            )

    def _get_item(self, item_id, session):
        raw_output = self._run("get", "item", item_id, "--session", session)
        return json.loads(raw_output)
