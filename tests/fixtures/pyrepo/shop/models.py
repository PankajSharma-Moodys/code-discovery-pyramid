"""Persistent models."""

import enum

from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.orm import declarative_base

from .util import slugify

Base = declarative_base()
metadata = MetaData()

audit_log = Table("audit_log", metadata, Column("id", Integer))


class Status(enum.Enum):
    NEW = "new"
    PAID = "paid"
    SHIPPED = "shipped"


class Customer:
    def __init__(self, name):
        self.name_value = name

    def name(self):
        return self.name_value


class Item:
    price: float = 0.0

    def __init__(self, price):
        self.price = price


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    status: Status = Status.NEW
    TAX_RATE = 0.2

    class Meta:
        ordering = "id"

    def __init__(self, items, customer=None):
        self.items = items
        self.customer = customer or Customer("anonymous")

    def total(self):
        return sum(item.price for item in self.items) * (1 + self.TAX_RATE)

    @property
    def label(self) -> str:
        return slugify("order " + str(self.id))

    @classmethod
    def empty(cls):
        return cls([])

    @staticmethod
    def make(items):
        return Order(items)

    def owner(self) -> Customer:
        return self.customer
