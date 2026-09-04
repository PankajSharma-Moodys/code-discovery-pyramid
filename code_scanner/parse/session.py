"""Grammar loading with a per-process parser cache.

R29: Python 3.14 removed `fork` as a default everywhere (not just darwin), so the
cache initialises lazily inside whichever process calls get_parser() — safe under
`spawn` and under a plain single-process call alike.
"""

from __future__ import annotations

from tree_sitter import Parser
from tree_sitter_language_pack import get_language

_parser_cache: dict[str, Parser] = {}


def get_parser(grammar: str) -> Parser:
    parser = _parser_cache.get(grammar)
    if parser is None:
        parser = Parser(get_language(grammar))
        _parser_cache[grammar] = parser
    return parser
