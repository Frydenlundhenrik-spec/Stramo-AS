"""HTTPS client for Stramo's shared, persistent account service."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

DEFAULT_ORIGIN = "https://stramo-flyt-time-avvik.candid-pine-4284.chatgpt.site"


class LoginError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def request(action, payload=None, token=None):
    origin = os.environ.get("STRAMO_ACCOUNT_ORIGIN", DEFAULT_ORIGIN).rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")):
        raise LoginError("Innloggingstjenesten er ikke riktig konfigurert.")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(origin + "/api/portal/" + action, data=data, headers=headers)
    try:
        with urlopen(req, timeout=20) as response:
            result = json.load(response)
    except HTTPError as exc:
        try:
            message = json.load(exc).get("error", "Innloggingen lyktes ikke.")
        except (ValueError, OSError):
            message = "Innloggingen lyktes ikke. Prøv igjen."
        raise LoginError(message, exc.code) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise LoginError("Innloggingstjenesten svarer ikke akkurat nå. Prøv igjen om litt.") from None
    if not isinstance(result, dict):
        raise LoginError("Uventet svar fra innloggingstjenesten.")
    return result
