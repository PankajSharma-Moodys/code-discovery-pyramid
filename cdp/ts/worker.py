"""Child process (JSON lines on stdin/stdout): the only place a grammar can crash the interpreter."""
import json
import sys
import traceback


def extender_errors():
    from . import engine, extender
    return (extender.NoRules, engine.GrammarMissing)


def handle(req):
    from . import baseline, extender
    data = req["src"].encode("utf8", "replace")
    if req["op"] == "extract":
        return extender.extract(data, req["lang"])
    if req["op"] == "baseline":
        return baseline.run(req["lang"], data)
    raise ValueError("unknown op %r" % req["op"])


def main():
    for line in sys.stdin:
        try:
            res = handle(json.loads(line))
        except (extender_errors()) as e:
            res = {"unsupported": str(e)}
        except Exception as e:
            res = {"error": "%s: %s" % (type(e).__name__, e), "tb": traceback.format_exc()[-400:]}
        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
