class Flask:
    def __init__(self, name):
        pass

    def route(self, path, **kw):
        return lambda f: f

    def add_url_rule(self, *a, **k):
        pass


class Blueprint(Flask):
    def __init__(self, name, import_name, url_prefix=None):
        pass
