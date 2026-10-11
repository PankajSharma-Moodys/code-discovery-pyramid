"""Django routes."""

from django.urls import include, path

from . import views

urlpatterns = [
    path("orders/", views.order_list),
    path("orders/<int:pk>/", views.order_detail),
    path("api/", include([path("ping/", views.ping)])),
]
