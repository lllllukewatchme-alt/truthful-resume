# Security policy

## Reporting a vulnerability
Please **do not open a public issue** for security problems. Use GitHub's private reporting:
repository **Security → Report a vulnerability**. If that is not available, e-mail **lllllukewatchme@gmail.com** with the
subject "truthful-resume security" (no real resumes or secrets in the message), or open an issue that only says "security
contact requested", without details.

Include: affected version (`VERSION`), what you did, what happened, and a **fictional** sample input. Never attach real resumes.

## What is in scope
- Overwriting or deleting files the user did not name (path handling, `--force`, installer).
- Writing resume content or personal data into reports/logs.
- Code execution through resume/JD content, or any network access (the toolkit is designed to be offline).
- Unsafe handling of the PDF backends (Word COM, LibreOffice) – e.g. leaving processes behind or touching the user's own Word.

## Secrets and personal data
- The toolkit needs **no API keys or accounts**. Never put keys, tokens, cookies or passwords into resume files, issues or pull requests.
- Resume files contain personal data. Keep your own resumes and generated outputs out of version control
  (`.gitignore` excludes `out/`, `*.docx`, `*.pdf` by default – check before you commit).
- If you accidentally committed a secret or personal data, treat it as exposed: revoke/rotate it, then remove it from history.

## Supported versions
Only the latest release receives fixes.
