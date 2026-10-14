"""Pusher: Function.prototype.bind is not an event; literal .subscribe('ch') is."""

import unittest

from tests.test_web import facts_of, edges

SRC = """import Pusher from 'pusher-js'
class C {
  init(y, name) {
    const pusher = new Pusher('k', {})
    const ch = pusher.subscribe('my-channel')
    pusher.subscribe(name)
    ch.bind('MyEvent', handler)
    this.onX = this.onX.bind(this, y)
    this.onY = this.onY.bind(null, y)
    const f = g.bind(this)
    this.channel.bind(topic, cb)
  }
}
"""


class PusherFlowFix(unittest.TestCase):
    def test_bind_this_not_event_and_channel_emitted(self):
        got = sorted(e["target"] for e in edges(facts_of("c.js", SRC), "event_subscribe"))
        self.assertEqual(got, ["event:${topic}", "event:MyEvent", "event:my-channel"])


if __name__ == "__main__":
    unittest.main()
