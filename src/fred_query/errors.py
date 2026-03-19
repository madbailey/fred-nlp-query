from __future__ import annotations


class FredQueryError(RuntimeError):
    """Base class for project-specific runtime failures."""


class ConfigurationError(FredQueryError):
    """Raised when required runtime configuration is missing or invalid."""


class UpstreamServiceError(FredQueryError):
    """Raised when an external service call fails."""

    def __init__(self, service: str, message: str) -> None:
        super().__init__(message)
        self.service = service


class IntentParsingError(UpstreamServiceError):
    """Raised when the OpenAI intent parsing call fails."""

    def __init__(self, message: str) -> None:
        super().__init__("openai", message)
