"""A tiny sample module used by the M0 walking-skeleton gate."""


def add(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b


class Greeter:
    def greet(self, name: str) -> str:
        if name:
            return f"Hello, {name}!"
        else:
            return "Hello!"
