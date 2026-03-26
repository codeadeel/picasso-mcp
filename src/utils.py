# %%
# Importing Necessary Libraries
import base64
import logging
from pathlib import Path
from datetime import datetime
from config import GOOGLE_API_KEY, OUTPUT_DIR

# %%
# Logger
logger = logging.getLogger(__name__)

# %%
# Utility Functions
def safeError(exc: Exception) -> str:
    """
    Returns a sanitized error string with the API key redacted.
    The Google SDK occasionally echoes the API key in error messages or URLs.
    Arguments:
    ----------
    exc : Exception
        The exception whose message should be sanitized.
    Returns:
    --------
    str
        Error message with the API key replaced by [REDACTED].
    """
    errorMsg = str(exc)
    if GOOGLE_API_KEY:
        errorMsg = errorMsg.replace(GOOGLE_API_KEY, "[REDACTED]")
    return errorMsg


def isImagen(model: str) -> bool:
    """
    Determines if the configured model belongs to the Imagen family.
    Imagen models use generate_images(); all others use generate_content().
    Arguments:
    ----------
    model : str
        The model name to check.
    Returns:
    --------
    bool
        True if the model name starts with "imagen", False otherwise.
    """
    return model.lower().startswith("imagen")


def saveImage(imageBytes: bytes, stem: str | None) -> Path:
    """
    Saves raw image bytes to a uniquely named PNG file in the output directory.
    Arguments:
    ----------
    imageBytes : bytes
        Raw PNG image data to write to disk.
    stem : str | None
        Optional base name for the file. A timestamp is always appended.
    Returns:
    --------
    Path
        Absolute path to the saved file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    rawName   = f"{stem}_{timestamp}" if stem else timestamp
    safeName  = "".join(c if c.isalnum() or c in "-_" else "_" for c in rawName)
    outPath   = OUTPUT_DIR / f"{safeName}.png"
    outPath.write_bytes(imageBytes)
    logger.info("Saved → %s", outPath)
    return outPath


def toBase64(data: bytes) -> str:
    """
    Encodes raw bytes to a base64 string.
    Arguments:
    ----------
    data : bytes
        Raw bytes to encode.
    Returns:
    --------
    str
        Base64-encoded UTF-8 string.
    """
    return base64.b64encode(data).decode()


def fromBase64(data: str | bytes) -> bytes:
    """
    Decodes a base64 string to bytes, or passes raw bytes through unchanged.
    Handles both return types that the Google SDK may produce.
    Arguments:
    ----------
    data : str | bytes
        Base64-encoded string or raw bytes from the SDK response.
    Returns:
    --------
    bytes
        Decoded raw bytes.
    """
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    return base64.b64decode(data)
