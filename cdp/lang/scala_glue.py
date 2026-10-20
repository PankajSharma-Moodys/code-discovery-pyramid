"""Bare test-DSL calls whose result xref cannot type (RC2).

`when(m.f(1)).thenReturn(x)`: `when` is a bare call, so the chain after it is typed on the spec and the
`.thenReturn` row can never resolve. Cutting the chain there is only done for a bare call, when the file
imports a test framework and declares no member of that name. Explicit-receiver calls are never touched.
"""

from __future__ import annotations

CHAIN_CUT_NAMES = frozenset(("when", "doReturn", "doThrow", "doAnswer"))
FRAMEWORK_PREFIXES = ("org.mockito", "org.scalatestplus.mockito", "org.scalatest", "org.scalamock")


def cuts_chain(name: str, declared, imported) -> bool:
    return (name in CHAIN_CUT_NAMES and name not in declared
            and any(i.startswith(FRAMEWORK_PREFIXES) for i in imported))
