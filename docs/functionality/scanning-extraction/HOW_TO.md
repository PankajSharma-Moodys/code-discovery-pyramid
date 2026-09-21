# How To — Scanning / Extraction (language extractors)

```bash
cdp scan --repo <path>              # writes ./.cdp/, renders docs by default
cdp scan --repo <path> --no-docs    # skip markdown rendering
cdp scan --repo <path> --workers N  # N=1 forces sequential extraction
cdp scan --repo <path> --exclude <segment>   # additional exclude, repeatable
cdp scan --in-repo                  # writes state to <repo>/.cdp, adds .gitignore entry
```

Add a language extractor: write an `Extractor` subclass in `cdp/lang/`,
register it in `cdp/lang/__init__.py`. Nothing else in the pipeline changes.

Team-wide excludes beyond `DEFAULT_EXCLUDES`: add an `exclude` array to
`.cdp.toml`.
