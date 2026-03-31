# %%
# Importing Necessary Libraries
import base64
import io
import logging
from pathlib import Path
from datetime import datetime
import httpx
from PIL import Image as PilImage
from fastmcp.exceptions import ToolError
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


def toThumbnail(imageBytes: bytes, maxSize: int = 800, quality: int = 75) -> bytes:
    """
    Creates a compressed JPEG thumbnail from raw image bytes.
    Used for inline display in clients that have message size limits.
    Arguments:
    ----------
    imageBytes : bytes
        Raw PNG image data.
    maxSize : int
        Maximum width or height in pixels. Aspect ratio is preserved.
        Default : 800
    quality : int
        JPEG compression quality (1-95).
        Default : 75
    Returns:
    --------
    bytes
        Compressed JPEG image bytes.
    """
    img = PilImage.open(io.BytesIO(imageBytes)).convert("RGB")
    img.thumbnail((maxSize, maxSize), PilImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


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


def _detectMime(data: bytes) -> str:
    if data[:8].startswith(b"\x89PNG"):              return "image/png"
    if data[:3] == b"\xff\xd8\xff":                  return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):           return "image/gif"
    if len(data) >= 12 and data[8:12] == b"WEBP":   return "image/webp"
    if data[:2] == b"BM":                            return "image/bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):        return "image/tiff"
    return "image/jpeg"


def loadImageBytes(source: str) -> tuple[bytes, str]:
    """
    Resolves an image source to (raw bytes, mime_type).
    Accepts:
      - Data URI:    "data:image/png;base64,<data>"
      - Raw base64:  plain base64 string
      - HTTPS URL:   fetched with httpx
      - Local file path
    Arguments:
    ----------
    source : str
        Image source string in any of the accepted formats.
    Returns:
    --------
    tuple[bytes, str]
        Raw image bytes and the detected/declared MIME type.
    Raises:
    -------
    ToolError
        On fetch failure, unreadable file, or unrecognized format.
    """
    src = source.strip()

    # Data URI: "data:image/png;base64,<payload>"
    if src.startswith("data:"):
        header, _, payload = src.partition(",")
        mimeType = header.split(";")[0][5:]  # strip "data:"
        return fromBase64(payload), mimeType

    # HTTPS URL
    if src.startswith("https://"):
        try:
            resp = httpx.get(src, follow_redirects=True, timeout=30, headers={"User-Agent": "PicassoMCP/1.0"})
            resp.raise_for_status()
        except Exception as exc:
            raise ToolError(f"Failed to fetch image URL: {exc}") from exc
        ct = resp.headers.get("content-type", "")
        mimeType = ct.split(";")[0].strip() if ct.startswith("image/") else _detectMime(resp.content)
        return resp.content, mimeType

    # HTTP rejected for security
    if src.startswith("http://"):
        raise ToolError("Only HTTPS URLs are supported for security reasons.")

    # Local file path
    path = Path(src)
    if path.exists() and path.is_file():
        data = path.read_bytes()
        return data, _detectMime(data)

    # Raw base64 fallback
    try:
        data = fromBase64(src)
        return data, _detectMime(data)
    except Exception as exc:
        raise ToolError(f"Unrecognized image source format: {exc}") from exc
