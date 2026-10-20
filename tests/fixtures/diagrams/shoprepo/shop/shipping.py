from shop.orders import OrderStatus


def ship(order):
    label = make_label(order.order_id)
    order.status = OrderStatus.SHIPPED
    return label


def make_label(order_id):
    return "LABEL-%s" % order_id
