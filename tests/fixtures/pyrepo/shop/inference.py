"""Receivers whose type has to be worked out."""

from typing import Generic, List, Optional, Tuple, TypeVar

from .models import Customer, Item, Order

T = TypeVar("T")
DEFAULT_ORDER = Order([])


class Box(Generic[T]):
    def get(self):
        return None


class OrderBox(Box[Order]):
    def first(self) -> Optional[Order]:
        return DEFAULT_ORDER


def pair() -> Tuple[Order, Customer]:
    return Order([]), Customer("pair")


def unpack():
    order, customer = pair()
    order.total()
    return customer.name()


def narrow(thing):
    if isinstance(thing, Order):
        return thing.total()
    return None


def loop(items: List[Item]):
    for item in items:
        item.price


class Context:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self):
        return "ran"


def withs():
    with Context() as ctx:
        return ctx.run()


class Lazy:
    size = property(lambda self: self.compute())

    def compute(self):
        return 3


def box_call():
    return OrderBox().first().total()


def make_order():
    return Order([])


def factory_chain():
    return make_order().owner().name()
