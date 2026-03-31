#!/usr/bin/env python3
# %%
# Importing Necessary Libraries
import logging
import uvicorn
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from config   import BASE_URL, GOOGLE_MODEL, GEMINI_MODEL, MCP_AUTH_TOKEN, MCP_HOST, MCP_PORT, MCP_TRANSPORT, OUTPUT_DIR, VALID_ASPECT_RATIOS
from auth     import BearerAuthMiddleware
from utils    import isImagen, safeError, saveImage
from backends import generateWithImagen, generateWithGemini, analyzeWithGemini

# %%
# Logger
logger = logging.getLogger(__name__)

# %%
# MCP Server Definition
_urlNote = (
    f"Generated images are accessible at {BASE_URL}/images/<filename>. "
    "Always share this URL with the user so they can view the full-quality image. "
    if BASE_URL else
    "Images are saved on the server filesystem. "
)
mcpServer = FastMCP(
    name         = "Picasso MCP",
    instructions = (
        "Generate images using Google AI Studio models (Imagen or Gemini). "
        f"Configured model: {GOOGLE_MODEL}. "
        "Call generateImage with a text prompt. "
        + _urlNote +
        "Do not attempt to read or copy image files — just share the URL from the tool result. "
        "Use analyzeImage to analyze, describe, edit, or answer questions about an existing image. "
        "It accepts the image as a base64 string (with or without data URI prefix), an HTTPS URL, or a server-side file path. "
        "Gemini decides whether to return text, an edited image, or both based on the prompt."
    ),
)

# %%
# MCP Tools
@mcpServer.tool()
def generateImage(
    prompt        : str,
    filename      : str | None = None,
    aspectRatio   : str        = "1:1",
    numberOfImages: int        = 1,
    negativePrompt: str | None = None,
) -> dict:
    """
    Generate one or more images from a text prompt using Google AI Studio.
    Works with Imagen (imagen-3.0-*) and Gemini (gemini-2.0-flash-exp, etc.) models.
    The generation backend is chosen automatically based on the GOOGLE_MODEL env variable.
    Arguments:
    ----------
    prompt : str
        Detailed description of the image to generate.
    filename : str | None
        Base name for saved files, no extension. Auto-generated if omitted.
    aspectRatio : str
        Output aspect ratio. One of: "1:1", "3:4", "4:3", "9:16", "16:9".
        Default : "1:1"
    numberOfImages : int
        How many images to generate (1-4). Gemini models make one API call per image.
        Default : 1
    negativePrompt : str | None
        What to avoid in the image. For Gemini models, appended to the prompt text.
    Returns:
    --------
    dict
        Contains model, prompt, aspectRatio, and a list of image results,
        each with path, base64 (PNG), and mime_type.
    """
    if aspectRatio not in VALID_ASPECT_RATIOS:
        raise ToolError(
            f"Invalid aspectRatio '{aspectRatio}'. "
            f"Valid options: {', '.join(sorted(VALID_ASPECT_RATIOS))}"
        )

    numberOfImages = max(1, min(4, numberOfImages))
    logger.info(
        "Generating %d image(s) | model=%s | aspectRatio=%s | prompt=%r",
        numberOfImages, GOOGLE_MODEL, aspectRatio, prompt[:120],
    )

    try:
        if isImagen(GOOGLE_MODEL):
            allBytes = generateWithImagen(prompt, aspectRatio, numberOfImages, negativePrompt)
        else:
            allBytes = generateWithGemini(prompt, aspectRatio, numberOfImages, negativePrompt)
    except ToolError:
        raise
    except Exception as exc:
        safeMsg = safeError(exc)
        logger.error("Generation error: %s", safeMsg)
        raise ToolError(f"Image generation failed: {safeMsg}") from exc

    if not allBytes:
        raise ToolError("No images were returned by the model.")

    imageResults = list()
    for idx, imageBytes in enumerate(allBytes):
        stem      = f"{filename}_{idx + 1}" if filename and numberOfImages > 1 else filename
        savedPath = saveImage(imageBytes, stem)
        info = {"path": str(savedPath)}
        if BASE_URL:
            info["url"] = f"{BASE_URL}/images/{savedPath.name}"
        imageResults.append(info)

    return {
        "model"      : GOOGLE_MODEL,
        "prompt"     : prompt,
        "aspectRatio": aspectRatio,
        "images"     : imageResults,
    }


@mcpServer.tool()
def analyzeImage(
    image   : str,
    prompt  : str        = "Describe this image in detail.",
    filename: str | None = None,
) -> dict:
    """
    Analyze, describe, or edit an image using Gemini.
    Provide an input image together with a text prompt. Gemini will return a text
    response, an edited/generated image, or both — depending on the prompt.
    The image parameter accepts any of these formats:
      - Base64 string with data URI prefix: "data:image/png;base64,<data>"
      - Raw base64 string (PNG, JPEG, WebP, GIF, BMP, TIFF)
      - HTTPS URL: "https://example.com/photo.jpg"
      - Local server file path: "/images/my_image.png"
    Arguments:
    ----------
    image : str
        The input image (base64, HTTPS URL, or file path).
    prompt : str
        Instruction for the model — e.g. "Describe this image", "Remove the background",
        "Convert to watercolor style". Default: "Describe this image in detail."
    filename : str | None
        Base name for the output image file (if the model produces one). Auto-generated if omitted.
    Returns:
    --------
    dict
        Contains model, prompt, and one or both of:
        - analysis (str): text response from the model
        - image (dict): path (and url if BASE_URL is set) of the saved output image
    """
    logger.info("Analyzing image | prompt=%r", prompt[:80])
    try:
        result = analyzeWithGemini(image, prompt)
    except ToolError:
        raise
    except Exception as exc:
        safeMsg = safeError(exc)
        logger.error("Vision analysis error: %s", safeMsg)
        raise ToolError(f"Image analysis failed: {safeMsg}") from exc

    response = {
        "model" : result["model"],
        "prompt": prompt,
    }

    if result["text"]:
        response["analysis"] = result["text"]

    if result["imageBytes"]:
        savedPath = saveImage(result["imageBytes"], filename)
        imageInfo = {"path": str(savedPath)}
        if BASE_URL:
            imageInfo["url"] = f"{BASE_URL}/images/{savedPath.name}"
        response["image"] = imageInfo

    return response


@mcpServer.tool()
def getServerInfo() -> dict:
    """
    Returns the current server configuration including model, output directory,
    supported aspect ratios, and whether authentication is enabled.
    Returns:
    --------
    dict
        Server configuration details.
    """
    modelFamily = "imagen" if isImagen(GOOGLE_MODEL) else "gemini"
    return {
        "model"              : GOOGLE_MODEL,
        "modelFamily"        : modelFamily,
        "geminiModel"        : GEMINI_MODEL,
        "outputDirectory"    : str(OUTPUT_DIR),
        "validAspectRatios"  : sorted(VALID_ASPECT_RATIOS),
        "maxImagesPerRequest": 4,
        "authEnabled"        : bool(MCP_AUTH_TOKEN),
        "note"               : (
            "Gemini models make one API call per image for numberOfImages > 1. "
            "aspectRatio is embedded in the prompt, not a native Gemini parameter."
            if modelFamily == "gemini" else
            "Imagen models support all parameters natively."
        ),
    }


@mcpServer.tool()
def listGeneratedImages(limit: int = 20) -> dict:
    """
    Lists recently generated images stored on the server, newest first.
    Arguments:
    ----------
    limit : int
        Maximum number of files to return. Capped between 1 and 100.
        Default : 20
    Returns:
    --------
    dict
        Output directory path and list of image details with path, sizeBytes, and name.
    """
    limit = max(1, min(100, limit))
    files = sorted(OUTPUT_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "outputDirectory": str(OUTPUT_DIR),
        "images"         : [
            {"path": str(f), "sizeBytes": f.stat().st_size, "name": f.name}
            for f in files[:limit]
        ],
    }

# %%
# Execution
if __name__ == "__main__":
    modelFamily = "imagen" if isImagen(GOOGLE_MODEL) else "gemini"

    if MCP_TRANSPORT == "stdio":
        logger.info(
            "Starting Picasso MCP | transport=stdio | model=%s | family=%s",
            GOOGLE_MODEL, modelFamily,
        )
        mcpServer.run(transport="stdio")
    elif MCP_AUTH_TOKEN:
        # Build a minimal pure-ASGI app wrapping the FastMCP SSE server with auth middleware.
        # Uses the MCP SDK's SseServerTransport directly so we control the ASGI layer and
        # can insert BearerAuthMiddleware without fighting FastMCP internals.
        # mcpServer._mcp_server is FastMCP's internal mcp.Server instance.
        from mcp.server.sse import SseServerTransport

        authStatus = "enabled"
        logger.info(
            "Starting Picasso MCP | transport=sse | model=%s | family=%s | auth=%s | port=%d",
            GOOGLE_MODEL, modelFamily, authStatus, MCP_PORT,
        )

        sse       = SseServerTransport("/messages/")
        rawServer = mcpServer._mcp_server

        async def _handleSse(scope: dict, receive: object, send: object) -> None:
            async with sse.connect_sse(scope, receive, send) as (readStream, writeStream):
                await rawServer.run(
                    readStream, writeStream,
                    rawServer.create_initialization_options(),
                )

        async def _baseApp(scope: dict, receive: object, send: object) -> None:
            if scope["type"] == "lifespan":
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                msg = await receive()
                if msg["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
            elif scope["type"] == "http":
                path   = scope.get("path", "")
                method = scope.get("method", "GET")
                if path == "/sse" and method == "GET":
                    await _handleSse(scope, receive, send)
                elif path.startswith("/messages/"):
                    await sse.handle_post_message(scope, receive, send)
                elif path.startswith("/images/"):
                    filename = path[len("/images/"):]
                    filepath = OUTPUT_DIR / filename
                    if filepath.exists() and filepath.suffix == ".png" and filepath.parent.resolve() == OUTPUT_DIR.resolve():
                        imageBytes = filepath.read_bytes()
                        await send({
                            "type"   : "http.response.start",
                            "status" : 200,
                            "headers": [
                                (b"content-type",   b"image/png"),
                                (b"content-length", str(len(imageBytes)).encode()),
                                (b"cache-control",  b"public, max-age=3600"),
                            ],
                        })
                        await send({"type": "http.response.body", "body": imageBytes})
                    else:
                        await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json")]})
                        await send({"type": "http.response.body", "body": b'{"error": "Not Found"}'})
                else:
                    body = b'{"error": "Not Found"}'
                    await send({
                        "type"   : "http.response.start",
                        "status" : 404,
                        "headers": [(b"content-type", b"application/json")],
                    })
                    await send({"type": "http.response.body", "body": body})

        uvicorn.run(BearerAuthMiddleware(_baseApp), host=MCP_HOST, port=MCP_PORT)
    else:
        logger.info(
            "Starting Picasso MCP | transport=sse | model=%s | family=%s | auth=disabled | port=%d",
            GOOGLE_MODEL, modelFamily, MCP_PORT,
        )
        mcpServer.run(transport="sse", host=MCP_HOST, port=MCP_PORT)
