"""Data only — rule 1."""

from code_scanner.languages.defs.typescript import PROFILE as _TS_PROFILE
from dataclasses import replace

PROFILE = replace(_TS_PROFILE, name="tsx", grammar="tsx", extensions=(".tsx",))
