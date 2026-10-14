"""JS/TS extractor: declarations, in-file HTTP wrappers, React Router routes, Pusher, module calls."""

import unittest

from cdp.lang.base import ExtractContext
from cdp.lang.web import WebExtractor
from cdp.lang.web_scan import scan

SERVICE = """import axios from 'axios'

class Svc {
  constructor(baseUrl) {
    this.baseUrl = baseUrl
  }

  getThing = (id) => {
    return this.callGet(`v3/things/${id}`).then((r) => r.data)
  }

  list = (limit) => {
    const filter = limit ? `&limit=${limit}` : ''
    const path = 'v1/things?'
      + `x=1${filter}`
    return this.callGet(path)
  }

  remove = (id) => this.callDelete(`v3/things/${id}`)

  callGet = (path) => {
    return axios.get(`${this.baseUrl}/${path}`, { headers: {} })
  }

  callDelete = (path) => {
    return axios.delete(`${this.baseUrl}/${path}`)
  }

  login = (name) => {
    return axios.post(
      `${this.baseUrl}/v1/login`,
      { name }
    )
  }

  sml = (path) => {
    const smlUrl = this.baseUrl.replace('/a', '/b')
    return axios.get(`${smlUrl}/${path}`)
  }

  callSml = (id) => this.sml(`quota/${id}`)
}

export default Svc
"""

ROUTES = """import { Route } from 'react-router-dom'
const R = () => (
  <ReactRoutes>
    <Route path="">
      <Route path="" element={<Main />}>
        <Route index element={<Home a={() => { return 1 }} />} />
      </Route>
      <Route path="workflows" element={<Auth><Layout /></Auth>}>
        <Route path="" element={<List />} />
        <Route path="detail/:id/" element={<Detail />} />
      </Route>
      <Route path="/abs" element={<A />} />
    </Route>
  </ReactRoutes>
)
"""

PUSHER = """import Pusher from 'pusher-js'
const EVENT = 'Status'
class P {
  register(topic, channelName, cb) {
    const pusher = new Pusher('key', {})
    const channel = pusher.subscribe(channelName)
    channel.bind(topic, cb)
  }
  literal(cb) {
    const pusher = new Pusher('key', {})
    pusher.subscribe('ch').bind(EVENT, cb)
  }
}
"""

PAGE = """import Svc from '../service/Svc'
import { helper, other as o } from './util'
class Page {
  load() {
    const svc = new Svc('x')
    svc.getThing(1)
    new Svc('y').list(2)
    helper(1)
  }
}
"""


def facts_of(path, text):
    return WebExtractor().extract(ExtractContext(path=path, lines=text.split("\n"), module="m"))


def edges(facts, channel):
    return [e for e in facts.io_edges if e["channel"] == channel]


class ScanTest(unittest.TestCase):
    def test_braces_in_strings_templates_regex_and_jsx(self):
        src = ["const a = '}{'", "const b = `x${ {k: 1}.k }}`", "const c = /[{]/.test(s)",
               "const d = <Foo>it's</Foo>", "function f() {", "  return 1", "}"]
        _, stacks, balanced = scan(src)
        self.assertTrue(balanced)
        self.assertEqual(stacks[4], ())
        self.assertEqual(stacks[5], ("{",))

    def test_jsx_close_tag_is_not_a_regex(self):
        _, _, balanced = scan(["const x = (", "  <Route a={1}></Route>", ")"])
        self.assertTrue(balanced)


class DeclTest(unittest.TestCase):
    def test_members_and_locals(self):
        f = facts_of("src/svc.js", SERVICE)
        by = {d["fqn"].split(".", 1)[1]: d for d in f.defines}
        self.assertEqual(by["Svc"]["kind"], "class")
        self.assertEqual(by["Svc.getThing"]["kind"], "method")
        self.assertEqual(by["Svc.constructor"]["kind"], "method")
        self.assertNotIn("filter", " ".join(by))          # locals are not symbols
        self.assertNotIn("smlUrl", " ".join(by))
        self.assertGreater(by["Svc"]["end_line"], by["Svc.login"]["end_line"])
        self.assertEqual(by["Svc.getThing"]["anchor"]["line"], 8)

    def test_top_level_constant_value_and_arrow(self):
        f = facts_of("a.js", "export const URL = '/v1/x'\nconst go = async (a) => {\n  const inner = 1\n}\n")
        kinds = {d["fqn"]: (d["kind"], d.get("value")) for d in f.defines}
        self.assertEqual(kinds["a.URL"], ("constant", "/v1/x"))
        self.assertEqual(kinds["a.go"][0], "method")
        self.assertNotIn("a.inner", kinds)

    def test_ts_visibility(self):
        f = facts_of("a.ts", "class A {\n  private x = 1\n  #y = 2\n  protected m(): void {}\n  n() {}\n}\n")
        vis = {d["fqn"]: d["visibility"] for d in f.defines}
        self.assertEqual((vis["a.A.x"], vis["a.A.#y"], vis["a.A.m"], vis["a.A.n"]),
                         ("private", "private", "protected", "public"))


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.out = {e["target"]: e for e in edges(facts_of("s.js", SERVICE), "http_out")}

    def test_wrapper_call_sites_resolved(self):
        self.assertIn("http:GET ${this.baseUrl}/v3/things/${id}", self.out)
        self.assertIn("http:DELETE ${this.baseUrl}/v3/things/${id}", self.out)

    def test_local_path_followed(self):
        hit = [t for t in self.out if t.startswith("http:GET ${this.baseUrl}/v1/things?x=1")]
        self.assertEqual(len(hit), 1)

    def test_multiline_call_argument(self):
        self.assertIn("http:POST ${this.baseUrl}/v1/login", self.out)

    def test_wrapper_placeholder_dropped(self):
        self.assertNotIn("http:GET ${this.baseUrl}/${path}", self.out)
        self.assertNotIn("http:DELETE ${this.baseUrl}/${path}", self.out)

    def test_unevaluable_local_keeps_its_name(self):
        self.assertIn("http:GET ${smlUrl}/quota/${id}", self.out)

    def test_source_is_the_calling_member(self):
        self.assertEqual(self.out["http:GET ${this.baseUrl}/v3/things/${id}"]["source"], "s.Svc.getThing")

    def test_wrapper_without_call_sites_keeps_its_edge(self):
        f = facts_of("w.js", "const get = (p) => axios.get(`${base}/api/${p}`)\n")
        self.assertEqual([e["target"] for e in edges(f, "http_out") if e["target"].startswith("http:")],
                         ["http:GET ${base}/api/${p}"])

    def test_literal_url_and_fetch_default_verb(self):
        f = facts_of("l.js", "function f() {\n  fetch('https://h/x')\n  axios.post('/y', {})\n}\n")
        self.assertEqual(sorted(e["target"] for e in edges(f, "http_out")),
                         ["http:GET https://h/x", "http:POST /y"])

    def test_unknown_url_not_emitted(self):
        f = facts_of("u.js", "function f(u) {\n  fetch(u)\n  axios.get(`${u}`)\n}\n")
        self.assertEqual(edges(f, "http_out"), [])


class RouteTest(unittest.TestCase):
    def test_react_router_nesting(self):
        paths = [e["target"] for e in edges(facts_of("r.js", ROUTES), "ui_route")]
        self.assertEqual(paths, ["ui_route:/", "ui_route:/workflows", "ui_route:/workflows/detail/:id/",
                                 "ui_route:/abs"])

    def test_express_routes_kept(self):
        f = facts_of("e.js", "app.get('/a/:id', h)\nrouter.post('/b', h)\n")
        self.assertEqual(sorted(e["target"] for e in edges(f, "http_in")), ["route:GET /a/:id", "route:POST /b"])

    def test_env_read_kept(self):
        f = facts_of("c.js", "const x = process.env.FOO\n")
        self.assertEqual([e["target"] for e in edges(f, "config_read")], ["config:FOO"])


class PusherTest(unittest.TestCase):
    def test_bind_is_a_subscription(self):
        f = facts_of("p.js", PUSHER)
        got = sorted((e["source"], e["target"]) for e in edges(f, "event_subscribe"))
        self.assertEqual(got, [("p.P.literal", "event:Status"), ("p.P.register", "event:${topic}")])

    def test_no_pusher_no_edge(self):
        self.assertEqual(edges(facts_of("q.js", "x.bind(this)\n"), "event_subscribe"), [])


class ModuleCallTest(unittest.TestCase):
    def test_calls_across_modules(self):
        f = facts_of("src/pages/Page.js", PAGE)
        calls = {(u["fqn"], u["from_symbol"]) for u in f.uses if u.get("kind") == "call"}
        self.assertIn(("src/service/Svc.Svc#getThing", "src/pages/Page.Page.load"), calls)
        self.assertIn(("src/service/Svc.Svc#list", "src/pages/Page.Page.load"), calls)
        self.assertIn(("src/pages/util.helper", "src/pages/Page.Page.load"), calls)


if __name__ == "__main__":
    unittest.main()
