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
