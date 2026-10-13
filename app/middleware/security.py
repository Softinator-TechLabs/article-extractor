from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Zero-overhead ASGI middleware injecting defensive security headers."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-content-type-options", "nosniff")
                headers.setdefault("x-frame-options", "DENY")
                headers.setdefault("referrer-policy", "strict-origin-when-cross-origin")
                headers.setdefault("permissions-policy", "geolocation=(), camera=(), microphone=()")

                # Check if connection was TLS or behind TLS-terminating reverse proxy
                scheme = scope.get("scheme", "http")
                headers_dict = dict(scope.get("headers", []))
                x_proto = headers_dict.get(b"x-forwarded-proto", b"").decode("latin-1")
                if scheme == "https" or x_proto == "https":
                    headers.setdefault(
                        "strict-transport-security", "max-age=31536000; includeSubDomains"
                    )

            await send(message)

        await self.app(scope, receive, send_with_security_headers)
