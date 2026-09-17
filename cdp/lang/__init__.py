"""Extractor registry — the portability seam.

To support a new language, write an `Extractor` subclass and add it to
`EXTRACTORS`. Nothing else in CDP needs to change: the channel vocabulary, the
patch schema, verification, merge, and every query are defined over the output
shape, not over any language.

Resolution order is exact filename, then extension, then the generic fallback.
Exact names win because `Dockerfile` and `Makefile` have no extension, and
`build.gradle` must be read as a manifest rather than as Groovy.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .base import ExtractContext, Extractor, FileFacts
from .build import MANIFEST_NAMES, BuildExtractor
from .csharp import CSharpExtractor
from .data import ConfigExtractor, DockerExtractor, GenericExtractor, SqlExtractor
from .go import GoExtractor
from .java import JavaExtractor
from .python import PythonExtractor
from .scala import ScalaExtractor
from .web import WebExtractor

EXTRACTORS: Tuple[Extractor, ...] = (
    BuildExtractor(),
    DockerExtractor(),
    JavaExtractor(),
    PythonExtractor(),
    WebExtractor(),
    GoExtractor(),
    CSharpExtractor(),
    ScalaExtractor(),
    SqlExtractor(),
    ConfigExtractor(),
)
_FALLBACK = GenericExtractor()

_BY_NAME: Dict[str, Extractor] = {}
_BY_EXT: Dict[str, Extractor] = {}
for _ex in EXTRACTORS:
    for _name in _ex.names:
        _BY_NAME[_name] = _ex
    for _suffix in _ex.extensions:
        _BY_EXT.setdefault(_suffix, _ex)

# Test detection. Kept in one place because §4.1 lists "what the tests reveal
# about intended behaviour" as a discovery facet, and a leaf that cannot tell
# production code from tests will describe a mock as if it were the design.
_TEST_PATTERNS = (
    re.compile(r"(^|/)(tests?|spec|specs|__tests__|testing)(/|$)"),
    re.compile(r"(^|/)src/(test|it|integrationTest)/"),
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"[^/]+_test\.(go|py|rb|js|ts)$"),
    re.compile(r"[^/]+(Test|Tests|IT|Spec)\.(java|kt|scala|cs)$"),
    re.compile(r"[^/]+\.(test|spec)\.(js|jsx|ts|tsx|mjs)$"),
)

_DOC_PATTERN = re.compile(r"\.(md|rst|adoc|txt)$", re.I)
_ASSET_PATTERN = re.compile(r"\.(png|jpe?g|gif|svg|ico|woff2?|ttf|eot|otf|pdf|jar|zip)$", re.I)
_CI_PATTERN = re.compile(r"(^|/)(\.github|\.gitlab|\.circleci|\.azure|ci|\.buildkite)(/|$)")


def get_extractor(path: str) -> Extractor:
    name = path.rsplit("/", 1)[-1]
    if name in _BY_NAME:
        return _BY_NAME[name]
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()
        if suffix in _BY_EXT:
            return _BY_EXT[suffix]
    return _FALLBACK


def classify_role(path: str, extractor: Extractor) -> str:
    """One of: test, build, schema, config, docs, asset, ci, source."""
    if any(p.search(path) for p in _TEST_PATTERNS):
        return "test"
    if _CI_PATTERN.search(path):
        return "ci"
    if extractor.role != "source":
        return extractor.role
    if _ASSET_PATTERN.search(path):
        return "asset"
    if _DOC_PATTERN.search(path):
        return "docs"
    return "source"


def is_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in MANIFEST_NAMES:
        return True
    return name.endswith((".csproj", ".fsproj", ".vbproj"))


def extract_file(path: str, lines: List[str], module: str) -> FileFacts:
    extractor = get_extractor(path)
    ctx = ExtractContext(path=path, lines=lines, module=module)
    try:
        return extractor.extract(ctx)
    except Exception as exc:  # a broken file must not abort a 391-file run
        facts = FileFacts(path=path, language=extractor.language, loc=len(lines))
        facts.notes.append("extractor_error:%s: %s" % (type(exc).__name__, exc))
        return facts


__all__ = [
    "EXTRACTORS",
    "ExtractContext",
    "Extractor",
    "FileFacts",
    "classify_role",
    "extract_file",
    "get_extractor",
    "is_manifest",
]
