from shop import Order, slugify
from shop.service import OrderService


def test_place():
    service = OrderService(None)
    service.place([])
    assert slugify("A b") == "a-b"
    assert Order([]).total() == 0
