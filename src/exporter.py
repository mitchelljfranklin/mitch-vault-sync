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
        self.mp = os.getenv("VAULTWARDEN_MP", "")
        self.client_id = os.getenv("VAULTWARDEN_CLIENT_ID")
        self.client_secret = os.getenv("VAULTWARDEN_CLIENT_SECRET")
        self.email = os.getenv("VAULTWARDEN_EMAIL")
        self.password = os.getenv("VAULTWARDEN_PASSWORD")
        self.max_workers = int(os.getenv("EXPORT_WORKERS", "10"))

    def _bw_path(self):
        for p in ["bw", "/usr/local/bin/bw"]:
            if shutil.which(p):
                return p
        return "bw"

    def _run(self, *args, env=None, stdin=None, timeout=120):
        cmd = [self._bw_path(), *args]
        logger.debug("bw: %s", " ".join(str(a) for a in args))

        proc_env = os.environ.copy()
        proc_env["BW_DATA_DIR"] = self.data_dir
        if env:
            proc_env.update(env)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=proc_env,
            timeout=timeout,
            input=stdin,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"bw {' '.join(args)} failed: {result.stderr.strip()}"
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
                    env={
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
                    env={"BW_PASSWORD": self.password},
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
            items_raw = self._run("list", "items", "--session", session)
            items = json.loads(items_raw)
            logger.info("Found %d items", len(items))

            if not items:
                logger.warning("No items found in vault")
                cache = {
                    "items": [],
                    "folders": [],
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                }
                with open(self.cache_path, "w") as f:
                    json.dump(cache, f)
                return cache

            # 5. Fetch full items in parallel
            logger.info(
                "Fetching %d items (%d workers)...",
                len(items),
                self.max_workers,
            )
            full_items = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = {
                    ex.submit(self._get_item, i["id"], session): i
                    for i in items
                }
                for idx, fut in enumerate(as_completed(futures), 1):
                    item = fut.result()
                    full_items.append(item)
                    logger.debug(
                        "[%d/%d] %s", idx, len(items), item.get("name", "Unknown")
                    )

            # 6. Get folders
            logger.debug("Fetching folders...")
            folders_raw = self._run("list", "folders", "--session", session)
            folders = json.loads(folders_raw)
            logger.info("Found %d folders", len(folders))

            # 7. Save cache
            cache = {
                "items": full_items,
                "folders": folders,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.cache_path, "w") as f:
                json.dump(cache, f, indent=2, default=str)

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
                env={"BW_PASSWORD": self.mp},
            )

    def _get_item(self, item_id, session):
        raw = self._run("get", "item", item_id, "--session", session)
        return json.loads(raw)
