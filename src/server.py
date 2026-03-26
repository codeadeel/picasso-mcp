#!/usr/bin/env python3
# %%
# Importing Necessary Libraries
import logging
import uvicorn
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from config   import GOOGLE_MODEL, MCP_AUTH_TOKEN, MCP_HOST, MCP_PORT, MCP_TRANSPORT, OUTPUT_DIR, VALID_ASPECT_RATIOS
from auth     import BearerAuthMiddleware
from utils    import isImagen, safeError, saveImage, toBase64
from backends import generateWithImagen, generateWithGemini

# %%
# Logger
logger = logging.getLogger(__name__)

# %%
# MCP Server Definition
mcpServer = FastMCP(
    name         = "Picasso MCP",
    instructions = (
        "Generate images using Google AI Studio models (Imagen or Gemini). "
        f"Configured model: {GOOGLE_MODEL}. "
        "Call generateImage with a text prompt. Images are returned as base64 PNG data."
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
        imageResults.append({
            "path"     : str(savedPath),
            "base64"   : toBase64(imageBytes),
            "mime_type": "image/png",
        })

    return {
        "model"      : GOOGLE_MODEL,
        "prompt"     : prompt,
        "aspectRatio": aspectRatio,
        "images"     : imageResults,
    }


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
                path = scope.get("path", "")
                if path == "/sse":
                    await _handleSse(scope, receive, send)
                elif path.startswith("/messages/"):
                    await sse.handle_post_message(scope, receive, send)
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
