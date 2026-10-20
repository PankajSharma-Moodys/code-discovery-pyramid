"""Scala test-DSL glue that xref always drops (RC2).

A strict `Type#name` row survives xref only if some repo type declares a method `name`. These names are
ScalaTest / Mockito / assertion vocabulary: measured on a real Scala service, none was ever the target
of a stored use. Dropping them in the extractor saves anchor matching, JSON and resolve work for rows
that cannot appear in any answer. The guard: a file that declares a member of the same name keeps its rows.
"""

from __future__ import annotations

GLUE_NAMES = frozenset((
    # ScalaTest flatspec / funsuite / matchers
    "when", "in", "should", "shouldBe", "shouldEqual", "of", "before", "include", "be", "test", "equal",
    "contain", "ignore", "intercept", "thrownBy", "fail", "assert", "assume", "assertThrows", "not",
    "startWith", "theSameElementsAs",
    # Mockito matchers / verification modes / stubbing
    "any", "anyString", "anyBoolean", "anyLong", "anyInt", "times", "never", "atLeastOnce", "eqTo", "meq",
    "doNothing", "doAnswer", "doThrow", "mock",
    # Predef
    "println",
))


def is_glue(name: str, declared) -> bool:
    return name in GLUE_NAMES and name not in declared
