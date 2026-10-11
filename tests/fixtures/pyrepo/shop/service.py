"""Order placement."""

import shop.util as shop_util
from billing.core import charge
from . import util
from .base import Service
from .models import Customer, Order, Status
from .repo import OrderRepo
from .util import region, slugify as slug


class OrderService(Service):
    def __init__(self, repo: OrderRepo):
        super().__init__()
        self.repo = repo
        self.customer = Customer("shop")

    def place(self, items):
        order = Order(items)
        order.total()
        self.repo.save(order)
        self.audit(order)
        charge(order)
        return slug("x") + region() + util.slugify("y") + shop_util.slugify("z")

    def audit(self, order):
        return super().audit(order) + str(Status.PAID)

    def rebuild(self):
        return Order.empty().label

    def labels(self, names):
        return list(map(slug, names))

    def owner_name(self, order: Order):
        return order.owner().name()
