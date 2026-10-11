class APIRouter:
    def __init__(self, prefix=""):
        pass

    def get(self, path):
        return lambda f: f

    def post(self, path):
        return lambda f: f


class FastAPI(APIRouter):
    def __init__(self):
        pass
