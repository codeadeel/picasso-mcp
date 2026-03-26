# %%
# Importing Necessary Libraries
import os
import logging
from pathlib import Path
from google import genai

# %%
# Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# %%
# Environment Configuration
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_MODEL   = os.environ.get("GOOGLE_MODEL", "imagen-3.0-generate-002")
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
OUTPUT_DIR     = Path(os.environ.get("OUTPUT_DIR", "/images"))
MCP_HOST       = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT       = int(os.environ.get("MCP_PORT", "8000"))
MCP_TRANSPORT  = os.environ.get("MCP_TRANSPORT", "sse")

if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY environment variable is required")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# %%
# Google GenAI Client Initialization
googleClient = genai.Client(api_key=GOOGLE_API_KEY)

# %%
# Constants
VALID_ASPECT_RATIOS = {"1:1", "3:4", "4:3", "9:16", "16:9"}
