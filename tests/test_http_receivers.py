"""HTTP client edges need a receiver that is provably an HTTP client and a URL-shaped first argument."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401

from cdp.lang.base import ExtractContext
from cdp.lang.csharp import CSharpExtractor
from cdp.lang.python import PythonExtractor


def py_targets(src, path="svc/api.py"):
    facts = PythonExtractor().extract(ExtractContext(path=path, lines=src.splitlines(), module="root"))
    return [e["target"] for e in facts.io_edges if e["channel"] == "http_out" and e["target"].startswith("http:")]


def cs_targets(src, path="Svc/Api.cs"):
    facts = CSharpExtractor().extract(ExtractContext(path=path, lines=src.splitlines(), module="m"))
    return [e["target"] for e in facts.io_edges if e["channel"] == "http_out" and e["target"].startswith("http:")]


class PythonReceiverTest(unittest.TestCase):
    def test_flask_session_and_cache_client_are_not_http(self):
        src = ('import requests\nfrom flask import session\n\n\ndef cart():\n    return session.get("cart/items")\n\n\n'
               'class Cache:\n    def f(self):\n        return self.client_cache.get("tenant/settings")\n'
               '    def g(self, client_cache):\n        return client_cache.get("tenant/settings")\n')
        self.assertEqual([], py_targets(src))

    def test_dict_like_get_is_not_http(self):
        self.assertEqual([], py_targets('import requests\n\n\ndef f(d, s):\n    d.get("a/b")\n    s.get("a/b")\n'))

    def test_a_non_url_first_argument_is_not_an_edge(self):
        src = 'import requests\ns = requests.Session()\ns.get("some key")\ns.get("plain")\nrequests.get("a b/c")\n'
        self.assertEqual([], py_targets(src))

    def test_provable_clients_still_match(self):
        src = ('import requests\nimport httpx\nimport aiohttp as ah\nfrom requests import Session\n\n'
               's = requests.Session()\nc: httpx.Client = httpx.Client(base_url="x")\n\n\n'
               'def a(sess: requests.Session, other):\n    sess.get("/a")\n    other.get("/not")\n\n\n'
               'async def b():\n    async with ah.ClientSession() as http:\n        await http.post("/b")\n\n\n'
               'class K:\n    def __init__(self):\n        self.api = Session()\n    def f(self):\n'
               '        return self.api.delete("/c/1")\n\n\n'
               'def d():\n    requests.get("http://h/d")\n    s.get("/e")\n    c.put("/f")\n')
        self.assertEqual(["http:GET /a", "http:POST /b", "http:DELETE /c/1", "http:GET http://h/d",
                          "http:GET /e", "http:PUT /f"], py_targets(src))


CS_OK = '''using System.Net.Http;
namespace A;
public class Api
{
    private readonly HttpClient _http;
    private readonly IHttpClientFactory _factory;
    public Api(HttpClient http, IHttpClientFactory factory) { _http = http; _factory = factory; }
    public async Task Run(int id)
    {
        await _http.GetAsync($"{BaseUrl}/tenant/{id}");
        var c = _factory.CreateClient("x");
        await c.PostAsJsonAsync("/orders", id);
        await _factory.CreateClient().DeleteAsync("/gone/1");
        await new HttpClient().GetStringAsync("http://h/ping");
        await _http
            .PutAsync("/fluent", null);
    }
}
'''
CS_BAD = '''using System.Net.Http;
namespace A;
public class Repo
{
    private readonly HttpClient _http;
    private readonly IStore _store;
    public async Task Run(int id)
    {
        await _store.GetAsync("a/b");
        await _cache.GetStringAsync("tenant/settings");
        await _http.GetAsync("some key");
        await _http.GetAsync(id.ToString());
        await GetRepo(_http).GetAsync("/x/y");
    }
}
'''


class CSharpReceiverTest(unittest.TestCase):
    def test_typed_and_created_clients_match(self):
        self.assertEqual(["http:GET /tenant/{id}", "http:POST /orders", "http:DELETE /gone/1",
                          "http:GET http://h/ping", "http:PUT /fluent"], cs_targets(CS_OK))

    def test_other_receivers_and_non_url_arguments_do_not(self):
        self.assertEqual([], cs_targets(CS_BAD))


if __name__ == "__main__":
    unittest.main()
