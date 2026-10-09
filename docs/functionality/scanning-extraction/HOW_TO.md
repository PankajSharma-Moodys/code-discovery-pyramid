# How To — Scanning / Extraction (language extractors)

```bash
cdp scan --repo <path>              # writes ~/.cdp (CDP_HOME), renders docs by default
cdp scan --repo <path> --no-docs    # skip markdown rendering
cdp scan --repo <path> --workers N  # N=1 forces sequential extraction
cdp scan --repo <path> --exclude <segment>   # additional exclude, repeatable
CDP_HOME=/tmp/h cdp scan --repo <path>   # a different store (--state-dir is an alias)
```

Add a language extractor: write an `Extractor` subclass in `cdp/lang/`,
register it in `cdp/lang/__init__.py`. Nothing else in the pipeline changes.

Team-wide excludes beyond `DEFAULT_EXCLUDES`: add an `exclude` array to
`.cdp.toml`.
