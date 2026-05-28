import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from app.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class TexExtractor(BaseExtractor):
    """Extract text from LaTeX (.tex) documents.

    Primary: TexSoup-based structured extraction.
    Fallback: regex-based command stripping.
    """

    _HEADING_MAP = {
        "section": "# ",
        "subsection": "## ",
        "subsubsection": "### ",
        "chapter": "# ",
        "paragraph": "#### ",
        "subparagraph": "##### ",
    }

    _STRIP_COMMANDS = {"cite", "ref", "label", "footnote", "bibliography", "bibliographystyle"}

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def extract(self, content: bytes, filename: str = "") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._sync_extract, content, filename)

    def _sync_extract(self, content: bytes, filename: str = "") -> str:
        text = content.decode("utf-8", errors="replace")
        try:
            return self._extract_with_texsoup(text)
        except Exception as exc:
            logger.warning(
                "TexSoup failed for %s (%s), falling back to regex",
                filename,
                type(exc).__name__,
            )
            return self._extract_with_regex(text)

    def _extract_with_texsoup(self, text: str) -> str:
        from TexSoup import TexSoup

        soup = TexSoup(text)
        parts: list[str] = []
        self._walk_node(soup, parts)
        return "\n\n".join(p.strip() for p in parts if p.strip())

    def _walk_node(self, node, parts: list[str]) -> None:
        """Recursively walk TexSoup tree and extract text."""
        if isinstance(node, str):
            parts.append(node)
            return

        node_name = getattr(node, "name", None)

        # Skip commands we want to strip
        if node_name in self._STRIP_COMMANDS:
            return

        # Handle headings
        if node_name in self._HEADING_MAP:
            prefix = self._HEADING_MAP[node_name]
            # Get the heading text from the first argument
            args = list(node.args) if hasattr(node, "args") else []
            if args:
                heading_text = str(args[0]).strip("{}")
                parts.append(f"{prefix}{heading_text}")
            return

        # Strip environment wrappers but keep content for math environments
        skip_envs = {"equation", "equation*", "align", "align*", "figure", "table"}
        if node_name in skip_envs:
            # Keep content text nodes inside
            for child in node:
                if isinstance(child, str):
                    parts.append(child.strip())
            return

        # Recurse into children
        try:
            for child in node:
                self._walk_node(child, parts)
        except TypeError:
            # Leaf node with no children
            text = str(node)
            if text.strip():
                parts.append(text.strip())

    @staticmethod
    def _extract_with_regex(text: str) -> str:
        """Fallback: strip LaTeX commands via regex."""
        # Remove comments
        text = re.sub(r"(?m)%.*$", "", text)
        # Remove \command[optional]{required} patterns
        text = re.sub(r"\\\w+(?:\[[^\]]*\])?\{([^}]*)\}", r"\1", text)
        # Remove remaining \commands without braces
        text = re.sub(r"\\\w+", "", text)
        # Remove \begin{...} and \end{...}
        text = re.sub(r"\\(?:begin|end)\{[^}]*\}", "", text)
        # Clean up extra whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
