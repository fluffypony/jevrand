class JevrandError(Exception):
    """Base error for failures callers can handle."""

    code = "jevrand_error"


class ValidationError(JevrandError):
    code = "invalid_input"


class ConfigurationError(JevrandError):
    code = "configuration_error"


class ProviderError(JevrandError):
    code = "provider_error"


class InvalidResponseError(JevrandError):
    code = "invalid_response"


class AttemptsExhaustedError(JevrandError):
    code = "attempts_exhausted"

    def __init__(self, attempts: int, last_result: object) -> None:
        self.attempts = attempts
        self.last_result = last_result
        super().__init__(f"Jev rejected all {attempts} candidates.")
