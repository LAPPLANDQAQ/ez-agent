"""Shared exception types for research execution failures."""


class ResearchExecutionError(Exception):
    """Base class for expected research execution failures."""


class SearchProviderError(ResearchExecutionError):
    """Raised when all search provider calls fail."""


class FetchProviderError(ResearchExecutionError):
    """Raised when all web fetch/read calls fail."""
