"""Extension -> LanguageProfile lookup. The only module that knows every language exists."""

from __future__ import annotations

from code_scanner.languages.defs import (
    cpp, csharp, go, java, javascript, python, ruby, rust, tsx, typescript,
)
from code_scanner.languages.profile import LanguageProfile

ALL_PROFILES: tuple[LanguageProfile, ...] = (
    python.PROFILE, javascript.PROFILE, typescript.PROFILE, tsx.PROFILE,
    go.PROFILE, java.PROFILE, rust.PROFILE, ruby.PROFILE, csharp.PROFILE, cpp.PROFILE,
)

# Longest-suffix-first so ".d.ts" style multi-dot extensions never lose to ".ts".
_BY_EXTENSION: dict[str, LanguageProfile] = {}
for _profile in ALL_PROFILES:
    for _ext in _profile.extensions:
        _BY_EXTENSION[_ext] = _profile

_BY_NAME: dict[str, LanguageProfile] = {p.name: p for p in ALL_PROFILES}


def profile_for_extension(extension: str) -> LanguageProfile | None:
    return _BY_EXTENSION.get(extension)


def profile_for_name(name: str) -> LanguageProfile | None:
    return _BY_NAME.get(name)


def profile_for_path(path: str) -> LanguageProfile | None:
    lower = path.lower()
    # Try compound suffixes (".d.ts") before the final one (".ts").
    parts = lower.split(".")
    for i in range(1, len(parts)):
        candidate = "." + ".".join(parts[i:])
        if candidate in _BY_EXTENSION:
            return _BY_EXTENSION[candidate]
    return None
