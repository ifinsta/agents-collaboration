## What this changes

## Edge cases

<!-- Which EC-NNN entries does this add or change? Is the status and the totals line in EDGE-CASES.md updated? -->

## Checklist

- [ ] `python -m ruff check .` is clean
- [ ] `python -m unittest discover -s tests -v` passes
- [ ] `python scripts/make_manifest.py --check` passes (run `python scripts/make_manifest.py` if the skill changed)
- [ ] New behaviour has a test named after its edge case
- [ ] Actual runtime/source/scope evidence is stated; unexecuted platforms remain owed
- [ ] Portable command arguments and explicit UTF-8 are preserved
- [ ] Current docs, historical evidence and breaking migrations are labeled accurately
