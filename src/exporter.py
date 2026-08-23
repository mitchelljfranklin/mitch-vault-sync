import os
import json

from .bw_cli import BitwardenCli
from .logger import get_logger

logger = get_logger(__name__)

EXPORT_PATH = "/data/vault_export.json"


class VaultwardenExporter(BitwardenCli):
    def __init__(self, export_path=EXPORT_PATH):
        super().__init__(data_dir="/data/vaultwarden")
        self.export_path = export_path
        self.url = os.getenv("VAULTWARDEN_URL", "").rstrip("/")
        self.master_password = os.getenv("VAULTWARDEN_MP", "")
        self.email = os.getenv("VAULTWARDEN_EMAIL", "")
        self.password = os.getenv("VAULTWARDEN_PASSWORD", "")

    def run(self):
        os.makedirs(self.data_dir, exist_ok=True)

        try:
            # 1. Configure server
            logger.info("Configuring Vaultwarden server: %s", self.url)
            self._run("config", "server", self.url)

            # 2. Login (Vaultwarden does not support API keys)
            logger.info("Logging into Vaultwarden...")
            self._run(
                "login",
                self.email,
                "--passwordenv",
                "BW_PASSWORD",
                extra_environment={"BW_PASSWORD": self.password},
            )

            # 3. Unlock (decryption always requires the master password)
            logger.debug("Unlocking vault...")
            session = self._run(
                "unlock",
                "--passwordenv",
                "BW_PASSWORD",
                "--raw",
                extra_environment={"BW_PASSWORD": self.master_password},
            )

            # 4. Export the whole vault in a single call
            logger.info("Exporting vault to %s...", self.export_path)
            self._run(
                "export",
                "--format",
                "json",
                "--output",
                self.export_path,
                "--session",
                session,
                timeout=600,
            )

            with open(self.export_path, encoding="utf-8") as export_file:
                exported_vault = json.load(export_file)

            item_count = len(exported_vault.get("items", []))
            folder_count = len(exported_vault.get("folders", []))
            if item_count == 0:
                logger.warning("Exported vault contains no items")

            logger.info(
                "Export complete: %d items, %d folders",
                item_count,
                folder_count,
            )
            return {
                "export_path": self.export_path,
                "item_count": item_count,
                "folder_count": folder_count,
            }

        finally:
            try:
                self._run("logout")
            except Exception:
                pass
