"""tree-sitter C parser lifecycle. No global state."""
import logging
from tree_sitter import Language, Parser
import tree_sitter_c as tsc

from module_a._ast_helpers import iter_all

logger = logging.getLogger(__name__)


def create_parser() -> Parser:
    """Create a fresh tree-sitter Parser for C. Caller owns the instance."""
    lang = Language(tsc.language())
    return Parser(lang)


def parse_file(parser: Parser, filepath: str) -> tuple:
    """Parse a C source file. Returns (root_node, source_bytes).

    Reports syntax errors via logging; never raises on parse errors.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    source_bytes = source.encode()
    tree = parser.parse(source_bytes)
    root = tree.root_node

    if root.has_error:
        for node in iter_all(root):
            if node.type == "ERROR":
                line = node.start_point[0] + 1
                logger.warning("%s:%d: syntax error, skipping affected code",
                               filepath, line)

    return root, source_bytes


class _FileParser:
    """Per-run file parser with AST caching and shared Parser instance.

    Parses each file once and caches the result. Subsequent calls to
    parse() for the same filepath return the cached (root, source_bytes).
    Call clear() to release cached AST memory when the pipeline is done.
    """

    def __init__(self):
        lang = Language(tsc.language())
        self._parser = Parser(lang)
        self._cache: dict[str, tuple] = {}

    def parse(self, filepath: str) -> tuple:
        """Parse a file, returning (root_node, source_bytes). Cached on first call."""
        if filepath in self._cache:
            return self._cache[filepath]

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        source_bytes = source.encode()
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        if root.has_error:
            for node in iter_all(root):
                if node.type == "ERROR":
                    line = node.start_point[0] + 1
                    logger.warning("%s:%d: syntax error, skipping affected code",
                                   filepath, line)

        self._cache[filepath] = (root, source_bytes)
        return self._cache[filepath]

    def clear(self):
        """Release all cached ASTs to free memory."""
        self._cache.clear()
