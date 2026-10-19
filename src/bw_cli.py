import os
import shutil
import subprocess
import time

from .logger import get_logger

logger = get_logger(__name__)

# Bitwarden Cloud throttles bulk vault operations and occasionally drops
# connections, so these failures are worth retrying with a backoff.
TRANSIENT_ERROR_MARKERS = (
    "rate limit",
    "too many requests",
    "temporarily unavailable",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "econnreset",
    "enotfound",
    "etimedout",
    "eai_again",
    "socket hang up",
    "timed out",
    'statuscode":429',
    'statuscode":502',
    'statuscode":503',
    'statuscode":504',
)


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

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=process_environment,
                timeout=timeout,
                input=standard_input,
            )
        except subprocess.TimeoutExpired:
            # TimeoutExpired embeds the full command, including the session key,
            # so it must never reach a log or an error message unchanged.
            raise RuntimeError(
                f"Bitwarden CLI command timed out after {timeout} seconds "
                f"({format_cli_arguments(arguments)})"
            ) from None
        if result.returncode != 0:
            raise RuntimeError(
                f"Bitwarden CLI command failed ({format_cli_arguments(arguments)}): "
                f"{result.stderr.strip()}"
            )
        return result.stdout.strip()

    def _run_with_retry(self, *arguments, max_attempts=5, initial_delay=5, **run_arguments):
        for attempt in range(1, max_attempts + 1):
            try:
                return self._run(*arguments, **run_arguments)
            except RuntimeError as error:
                if attempt == max_attempts or not self._is_transient_error(error):
                    raise
                delay_seconds = min(initial_delay * 2 ** (attempt - 1), 60)
                logger.warning(
                    "Bitwarden CLI request failed transiently on attempt %d of %d; "
                    "retrying in %d seconds: %s",
                    attempt,
                    max_attempts,
                    delay_seconds,
                    error,
                )
                time.sleep(delay_seconds)

    def _is_transient_error(self, error):
        error_message = str(error).lower()
        return any(marker in error_message for marker in TRANSIENT_ERROR_MARKERS)
