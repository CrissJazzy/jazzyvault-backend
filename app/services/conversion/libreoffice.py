import asyncio
import logging
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# LibreOffice headless instances can collide when run concurrently against
# the same user profile directory. This lock serializes conversions within
# a single backend process; fine for an MVP / free-tier deployment with
# low concurrent load. If this becomes a bottleneck, the standard fix is
# a small pool of long-lived soffice listener processes — out of scope
# for the MVP.
_soffice_lock = asyncio.Lock()

SOFFICE_TIMEOUT_SECONDS = 90


class ConversionError(Exception):
    pass


def _find_soffice_binary() -> str:
    for candidate in ("soffice", "libreoffice"):
        path = shutil.which(candidate)
        if path:
            return path
    raise ConversionError(
        "LibreOffice ('soffice') was not found on this system. "
        "It must be installed via the Dockerfile for DOCX<->PDF conversion to work."
    )


async def convert_with_libreoffice(
    input_path: Path, output_dir: Path, target_format: str
) -> Path:
    """
    Converts a document using LibreOffice headless mode.
    target_format: a LibreOffice export filter target, e.g. "pdf" or "docx".
    Returns the path to the converted file.
    """
    soffice = _find_soffice_binary()

    # Each call gets an isolated user profile directory to avoid
    # "soffice is already running" lock conflicts between concurrent
    # requests sharing the same default profile.
    profile_dir = output_dir / f".profile-{uuid.uuid4()}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    user_install_url = f"-env:UserInstallation=file://{profile_dir}"

    cmd = [
        soffice,
        "--headless",
        "--norestore",
        user_install_url,
        "--convert-to",
        target_format,
        "--outdir",
        str(output_dir),
        str(input_path),
    ]

    async with _soffice_lock:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=SOFFICE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise ConversionError(
                f"Conversion timed out after {SOFFICE_TIMEOUT_SECONDS} seconds."
            )
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)

    if proc.returncode != 0:
        logger.error("soffice conversion failed: %s", stderr.decode(errors="ignore"))
        raise ConversionError(
            f"LibreOffice conversion failed: {stderr.decode(errors='ignore')[:300]}"
        )

    expected_output = output_dir / f"{input_path.stem}.{target_format}"
    if not expected_output.exists():
        logger.error(
            "soffice reported success but output file is missing. stdout=%s",
            stdout.decode(errors="ignore"),
        )
        raise ConversionError(
            "Conversion completed but the output file could not be found."
        )

    return expected_output
