"""Django views and models."""

from django.db import models


class Invoice(models.Model):
    class Meta:
        db_table = "billing_invoice"


def order_list(request):
    return []


def order_detail(request, pk):
    return pk


def ping(request):
    return "pong"
