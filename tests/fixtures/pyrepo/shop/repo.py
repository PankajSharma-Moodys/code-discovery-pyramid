"""Raw SQL access."""


class OrderRepo:
    SCHEMA = """CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY)"""

    def __init__(self, conn):
        self.conn = conn

    def save(self, order):
        self.conn.execute("INSERT INTO orders (id) VALUES (?)", (order.id,))
        return order

    def find(self, order_id):
        """update body of the request; select what you need from the list"""
        # update the table of results once the select has finished
        rows = self.conn.execute(
            "SELECT o.id FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.id = ?",
            (order_id,),
        )
        return rows

    def close_old(self):
        self.conn.execute("DELETE FROM sessions WHERE expired = 1")
        return "update the cache and select the best"
