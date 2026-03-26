# %%
# Importing Necessary Libraries
import logging
from google.genai import types
from config import googleClient, GOOGLE_MODEL
from utils import fromBase64

# %%
# Logger
logger = logging.getLogger(__name__)

# %%
# Imagen Backend
def generateWithImagen(
    prompt        : str,
    aspectRatio   : str,
    numberOfImages: int,
    negativePrompt: str | None,
) -> list[bytes]:
    """
    Generates images via the Imagen API using generate_images().
    Arguments:
    ----------
    prompt : str
        Text description of the image to generate.
    aspectRatio : str
        Native aspect ratio parameter supported by Imagen.
    numberOfImages : int
        Number of images to generate in a single API call.
    negativePrompt : str | None
        Optional content to exclude from the image.
    Returns:
    --------
    list[bytes]
        List of raw PNG image bytes, one per generated image.
    """
    config = types.GenerateImagesConfig(
        number_of_images = numberOfImages,
        aspect_ratio     = aspectRatio,
        output_mime_type = "image/png",
        **({"negative_prompt": negativePrompt} if negativePrompt else {}),
    )
    response = googleClient.models.generate_images(
        model  = GOOGLE_MODEL,
        prompt = prompt,
        config = config,
    )
    return [img.image.image_bytes for img in response.generated_images]

# %%
# Gemini Backend
def generateWithGemini(
    prompt        : str,
    aspectRatio   : str,
    numberOfImages: int,
    negativePrompt: str | None,
) -> list[bytes]:
    """
    Generates images via the Gemini API using generate_content() with IMAGE modality.
    Aspect ratio and negative prompt are embedded into the prompt text since Gemini
    does not support them as native parameters. Multiple images require separate API calls.
    Arguments:
    ----------
    prompt : str
        Text description of the image to generate.
    aspectRatio : str
        Aspect ratio hint embedded into the prompt text.
    numberOfImages : int
        Number of images to generate — triggers one API call per image.
    negativePrompt : str | None
        Content to avoid, appended to the prompt text.
    Returns:
    --------
    list[bytes]
        List of raw PNG image bytes collected across all API calls.
    """
    ratioHint = {
        "1:1" : "square 1:1",           "16:9": "wide landscape 16:9",
        "9:16": "tall portrait 9:16",   "4:3" : "standard landscape 4:3",
        "3:4" : "standard portrait 3:4",
    }.get(aspectRatio, aspectRatio)

    fullPrompt = f"{prompt} (aspect ratio: {ratioHint})"
    if negativePrompt:
        fullPrompt += f". Do not include: {negativePrompt}"

    results = list()
    for i in range(numberOfImages):
        response = googleClient.models.generate_content(
            model    = GOOGLE_MODEL,
            contents = fullPrompt,
            config   = types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        imageFound = False
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    results.append(fromBase64(part.inline_data.data))
                    imageFound = True
                    break
            if imageFound:
                break
        if not imageFound:
            logger.warning("No image returned for Gemini call %d/%d", i + 1, numberOfImages)

    return results
