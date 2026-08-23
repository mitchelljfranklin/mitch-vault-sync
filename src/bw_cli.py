import os
import shutil
import subprocess

from .logger import get_logger

logger = get_logger(__name__)


def format_cli_arguments(arguments):
    # Session keys unlock the full vault, so they must never reach logs
    masked_parts = []
    mask_next_part = False
    for part in arguments:
        part = str(part)
        if mask_next_part:
            masked_parts.append("***session***")
            mask_next_part = False
        elif part == "--session":
            masked_parts.append(part)
            mask_next_part = True
        else:
            masked_parts.append(part)
    return " ".join(masked_parts)


class BitwardenCli:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    def _bw_path(self):
        for candidate_path in ["bw", "/usr/local/bin/bw"]:
            if shutil.which(candidate_path):
                return candidate_path
        return "bw"

    def _run(self, *arguments, extra_environment=None, standard_input=None, timeout=120):
        command = [self._bw_path(), *arguments]
        logger.debug("Bitwarden CLI: %s", format_cli_arguments(arguments))

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
                f"Bitwarden CLI command failed ({format_cli_arguments(arguments)}): "
                f"{result.stderr.strip()}"
            )
        return result.stdout.strip()
