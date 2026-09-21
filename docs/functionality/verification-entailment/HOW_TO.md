# How To — Verification / Entailment (`verify.py`, `entail.py`, `gates.py`)

```bash
cdp collect                     # validate -> verify anchors -> entail -> fold
cdp answer <scope> --subject S --kind K --claim "..." --anchor file:line \
    [--channel C] [--confidence L] [--author A]
cdp query unknowns [--json]
```

`cdp answer --kind`/`--channel` choices come straight from the schema's
closed enums — run `cdp answer --help` to see them; they cannot drift.
