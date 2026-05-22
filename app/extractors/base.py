from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    """Abstract base class for all document extractors."""

    @abstractmethod
    async def extract(self, content: bytes, filename: str = "") -> str:
        """Extract text content from raw document bytes.

        Args:
            content: Raw bytes of the document.
            filename: Optional original filename (used for logging/diagnostics).

        Returns:
            Extracted text content as a string.
        """
