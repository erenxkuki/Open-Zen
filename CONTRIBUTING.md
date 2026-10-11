# Contributing

- Python 3.10+, stdlib only for the core (keep installs trivial).
- Run `python -m unittest discover -s tests -v` before each PR.
- Add ISA ops only with spec entry + tests + docs; never reuse op IDs.
- Least privilege by default in examples and tests.
