# Assets

- `logo.png` — the Open Zen mark (white OZ monogram on black, as approved).
  Drop the file here; it is referenced by `README.md` (project header).
  Suggested: PNG ≥ 1024 px, plus an SVG twin (`logo.svg`) when available.
- `banner.txt` — the ASCII terminal banner + tagline. Canonical source is
  `openzen/banner.py` (single source of truth; this file mirrors it).
  Shown in `README.md`, `docs/architecture.md`, `python -m openzen banner`,
  server startup, and the demo. Regenerate by hand if the art changes.

Do not commit alternative marks without replacing all references.
