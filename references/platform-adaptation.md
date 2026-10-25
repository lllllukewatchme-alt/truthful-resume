# Platform adaptation

Principle: one core (`core/`, `references/`), one engine (`scripts/`, `resume_design/`), thin adapters
(`adapters/*`) that only differ in entry format and capability wording. Do not fork business logic per model.

## Which adapter, and what is honest to claim

| Platform | Can run scripts? | What the model should do |
|---|---|---|
| Claude Code / Codex | yes (shell) | follow SKILL.md; call scripts; read reports; hand back files |
| DeepSeek / Doubao / other chat UIs | no | gather facts, output `resume.json` in a code block, tell the user the 3 commands to run locally; offer to interpret the printed report |
| Chat UI with code interpreter | maybe | ask the user to upload the toolkit; stdlib-only so Python ≥3.9 suffices; PDF needs Word/LibreOffice, which sandboxes rarely have → expect `blocked_by_environment` |

## Adapter rules
1. Say what the adapter cannot do (no local file access, no PDF) up front, in one line.
2. Never claim the file exists unless a script printed `generated:`.
3. Never claim a platform "supports" the toolkit beyond the status in `core/platform-capabilities.md`.
4. Same placeholder (`{{MISSING:field}}`), same data model, same status words on every platform.
5. When capability detection is impossible (chat UI), ask the user: "Can you run Python commands locally?" and branch.

## Adding a platform
Copy `adapters/generic/PROMPT.md`, adjust the capability paragraph, add a row to `core/platform-capabilities.md`
as **spec-based** or **manual** (never **tested** until it was actually run there), and extend
`tests/test_platform_adapters.py` with its required phrases.
