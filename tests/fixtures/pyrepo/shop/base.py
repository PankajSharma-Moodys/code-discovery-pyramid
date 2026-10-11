"""Base classes."""


class Service:
    """Anything with a lifecycle."""

    def __init__(self):
        self.started = False

    def log(self, message):
        return "[service] " + message

    def audit(self, order):
        return self.log("audit " + str(order))
