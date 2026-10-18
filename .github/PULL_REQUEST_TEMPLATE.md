## What this changes

## Edge cases

<!-- Which EC-NNN entries does this add or change? Is the status and the totals line in EDGE-CASES.md updated? -->

## Checklist

- [ ] `python -m ruff check .` is clean
- [ ] `python -m unittest discover -s tests -v` passes
- [ ] `python scripts/make_manifest.py --check` passes (run `python scripts/make_manifest.py` if the skill changed)
- [ ] New behaviour has a test named after its edge case
- [ ] Works on Windows as well as Linux and macOS (argument lists, explicit UTF-8)
