# How To — Doctor / Model Conformance (`doctor.py`)

```bash
cdp doctor --runner-cmd "<model-runner-script> <model> <repo>" [--timeout N]
```

Writes `<state>/doctor/<model-label>.json`; prints a cross-model
compatibility table from every report already on disk.
