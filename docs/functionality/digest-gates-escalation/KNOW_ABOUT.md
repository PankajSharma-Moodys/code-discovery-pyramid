# Know About — Digest Gates & Escalation

- The escalation rate metric returns `None` (not `0.0`) for a batch with no
  claims, and is meaningless (prints a misleading `0.000`) for a batch that
  wasn't produced in digest mode at all — the patch schema carries no
  "which mode produced this batch" marker.
