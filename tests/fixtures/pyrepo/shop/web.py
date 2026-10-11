"""HTTP endpoints."""

from fastapi import APIRouter, FastAPI
from flask import Blueprint, Flask

from .service import OrderService

app = Flask(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")
api = FastAPI()
router = APIRouter(prefix="/v1")


@app.route("/health")
def health():
    return "ok"


@bp.route("/orders", methods=["GET", "POST"])
def orders():
    return OrderService(None).place([])


@router.get("/items/{item_id}")
async def item(item_id: int):
    return item_id


@api.post("/login")
def login():
    return "in"


def add_extra(application):
    application.add_url_rule("/extra", view_func=health, methods=["PUT"])
