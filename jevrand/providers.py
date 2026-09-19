import json
import math
import os
from dataclasses import dataclass, field
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import ConfigurationError, InvalidResponseError, ProviderError, ValidationError

PROVIDERS = {
    "typesafe": ("https://api.typesafe.ai/v1/systemone", "jev-latest", "TYPESAFE_API_KEY"),
    "openrouter": (
        "https://openrouter.ai/api/alpha/decisions",
        "~typesafe/jev-latest",
        "OPENROUTER_API_KEY",
    ),
}
MAX_RESPONSE_BYTES = 1_048_576


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a provider's credentials to a redirect target.
        return None


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    model: str
    api_key: str = field(repr=False)
    timeout: float

    @classmethod
    def configure(
        cls, name: str | None = None, api_key: str | None = None, timeout: float = 30
    ) -> "Provider":
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout <= 86400
            or not math.isfinite(timeout)
        ):
            raise ValidationError(
                "The timeout must be greater than zero and at most 86400 seconds."
            )
        if name is not None and (not isinstance(name, str) or name not in PROVIDERS):
            raise ConfigurationError("The provider must be typesafe or openrouter.")
        if api_key is not None and name is None:
            raise ConfigurationError("Specify a provider when you supply an API key.")
        if name is None:
            name = next(
                (p for p, (_, _, env) in PROVIDERS.items() if os.environ.get(env, "").strip()),
                None,
            )
        if name is None:
            raise ConfigurationError("Set TYPESAFE_API_KEY or OPENROUTER_API_KEY in your shell.")
        url, model, env = PROVIDERS[name]
        key = api_key if api_key is not None else os.environ.get(env, "")
        if not isinstance(key, str) or not key.strip():
            raise ConfigurationError(f"Set {env} for the {name} provider.")
        key = key.strip()
        if not key.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in key):
            raise ConfigurationError("The API key contains invalid characters.")
        return cls(name, url, model, key, float(timeout))

    def decide(self, state: dict, question: dict) -> str:
        payload = {"model": self.model, "state": state, "questions": {"verdict": question}}
        request = Request(
            self.url,
            data=json.dumps(payload, allow_nan=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "jevrand/0.1.0",
            },
            method="POST",
        )
        try:
            with build_opener(_NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            exc.close()
            hints = {
                401: "Check the API key.",
                402: "Check the account balance.",
                403: "Check the account's access to Jev.",
                422: "The provider rejected the request format.",
                429: "The rate limit was reached. Try again later.",
                529: "The provider is overloaded. Try again later.",
            }
            hint = hints.get(exc.code, "Try again later or check the provider's status.")
            # Provider bodies can echo headers. Do not include them in errors.
            raise ProviderError(f"{self.name} returned HTTP {exc.code}. {hint}") from None
        except (URLError, OSError, HTTPException):
            raise ProviderError(
                f"The {self.name} request failed or timed out. Check the connection and try again."
            ) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise InvalidResponseError("The provider response exceeded 1 MiB.")
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            raise InvalidResponseError("The provider did not return valid JSON.") from None
        if not isinstance(data, dict) or "error" in data:
            raise InvalidResponseError("The provider did not return a decision.")
        answers = data.get("answers")
        answer = answers.get("verdict") if isinstance(answers, dict) else None
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise InvalidResponseError("The provider did not return a choice for verdict.")
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in question["criteria"]:
            raise InvalidResponseError("The provider returned an unknown verdict.")
        return choice
