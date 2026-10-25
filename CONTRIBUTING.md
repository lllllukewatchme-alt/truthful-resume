# Contributing

Thanks for helping! This project is a **local, offline resume toolkit** (Python standard library only) plus
adapter files for AI assistants. Two rules shape every change:

1. **Truthfulness first** – nothing may be added that makes the tool invent employers, dates, certificates or metrics.
2. **Never claim what was not verified** – a platform/backend is "tested" only if someone actually ran it there.

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows;  source .venv/bin/activate on macOS/Linux
python scripts/inspect_environment.py
```
No runtime dependencies. Optional extras (`python-docx`, `pypdf`) and `pytest` are not required.

## Tests (must pass before a PR)
```bash
python -m unittest discover -s tests
```
- Tests use **fictional data and temporary folders only**. Never add a real person's resume, phone number, e-mail or address.
- Tests that need Microsoft Word / LibreOffice / `pdftotext` skip with an explicit `blocked_by_environment` reason.
  A skipped test is *not* a passing test; say in the PR which environment you ran on.
- Bug fixes: write the failing test first (see `tests/test_regressions.py`, `tests/test_gaps.py`).
- Run `python scripts/run_acceptance.py --output-dir <temp dir>` to regenerate the acceptance report; reports must not contain
  local user paths.

## Code style
- Python >= 3.9 syntax, standard library only, type hints where they help, short functions, clear error messages.
- Every CLI failure is a documented exit code (0 ok · 2 input · 3 dependency · 4 generation/export · 5 validation) with a one-line
  message – never a traceback. Never overwrite an existing file unless `--force` was given for that file.
- No network calls, no shelling out with `shell=True`, no logging of resume contents (use `redact`/`snippet`).

## Docs & adapters
- If you change a CLI option, update `README.md` (the test suite checks that README and `--help` agree).
- `adapters/*/SKILL.md` follow the official Claude Code / Codex skill formats; keep them short and put detail in `core/` and `references/`.
- Platform status lives in `core/platform-capabilities.md`. Use *tested / spec-based / manual / unsupported* honestly.

## Pull requests
Small, focused changes; describe the problem, the fix and how you tested it (command + environment). By contributing you agree
that your work is released under the MIT License.
