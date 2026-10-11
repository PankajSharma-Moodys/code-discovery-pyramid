"""Billing, laid out as `src/billing` and imported as `billing`."""

from .rates import vat_rate

FEE = 0.03


def charge(order):
    return order.total() * (1 + vat_rate() + FEE)
