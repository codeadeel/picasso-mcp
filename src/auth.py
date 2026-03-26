# %%
# Importing Necessary Libraries
from config import MCP_AUTH_TOKEN

# %%
# Bearer Authentication Middleware
class BearerAuthMiddleware:
    """
    Pure ASGI middleware that validates Bearer token authentication on all incoming HTTP requests.
    When MCP_AUTH_TOKEN is set, every request must include a matching Authorization header.
    Requests without a valid token receive a 401 Unauthorized response.
    Non-HTTP scopes (e.g. lifespan) are passed through without auth checks.
    """

    def __init__(self, app: object) -> None:
        """
        Initializes the middleware with the ASGI app to wrap.
        Arguments:
        ----------
        app : object
            The ASGI application to wrap with authentication.
        """
        self.app = app

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        """
        ASGI interface — validates Bearer token before forwarding HTTP requests.
        Arguments:
        ----------
        scope : dict
            ASGI connection scope containing request metadata.
        receive : object
            ASGI receive channel.
        send : object
            ASGI send channel.
        """
        if scope["type"] == "http":
            headers       = {k: v for k, v in scope.get("headers", [])}
            authHeader    = headers.get(b"authorization", b"").decode()
            incomingToken = authHeader.removeprefix("Bearer ").strip()
            if incomingToken != MCP_AUTH_TOKEN:
                errorBody = b'{"error": "Unauthorized - invalid or missing Bearer token"}'
                await send({
                    "type"    : "http.response.start",
                    "status"  : 401,
                    "headers" : [
                        (b"content-type",   b"application/json"),
                        (b"content-length", str(len(errorBody)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": errorBody})
                return
        await self.app(scope, receive, send)
