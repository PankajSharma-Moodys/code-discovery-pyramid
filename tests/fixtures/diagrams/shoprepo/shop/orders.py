from enum import Enum

from shop.payment import charge
from shop.shipping import ship


class OrderStatus(Enum):
    NEW = "new"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class Order:
    def __init__(self, order_id, amount):
        self.order_id = order_id
        self.amount = amount
        self.status = OrderStatus.NEW


def place_order(order_id, amount):
    order = Order(order_id, amount)
    if charge(order):
        order.status = OrderStatus.PAID
        ship(order)
    else:
        order.status = OrderStatus.CANCELLED
    return order
