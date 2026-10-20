def validate_amount(amount):
    return amount > 0


def charge(order):
    if not validate_amount(order.amount):
        return False
    return record_charge(order.order_id, order.amount)


def record_charge(order_id, amount):
    print("charged", order_id, amount)
    return True
