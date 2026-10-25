"""Shared helpers: exit codes, redaction, safe paths, atomic no-clobber writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_DEPENDENCY = 3
EXIT_GENERATION = 4
EXIT_VALIDATION = 5


def setup_console() -> None:
    """Never crash on unencodable characters when printing to a legacy console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


class ToolError(Exception):
    """Error carrying the process exit code to use."""

    def __init__(self, message: str, code: int = EXIT_INPUT):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- redaction
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ID18 = re.compile(r"\b\d{17}[\dXx]\b")
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s\-().]{6,}\d(?![\w])")


def redact(text: str) -> str:
    """Mask emails, ID numbers and phone numbers for logs and reports."""
    if not text:
        return text
    text = _EMAIL.sub(lambda m: m.group(0)[:1] + "***@***", text)
    text = _ID18.sub("[ID-REDACTED]", text)
    text = _PHONE.sub(lambda m: "***" + re.sub(r"\D", "", m.group(0))[-2:], text)
    return text


def snippet(text: str, n: int = 24) -> str:
    """Short, redacted excerpt suitable for reports."""
    text = redact(" ".join(str(text).split()))
    return text if len(text) <= n else text[:n] + "..."


# ---------------------------------------------------------------- hashing / io
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_file(path: Path) -> str:
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise ToolError(f"cannot read input file: {e.strerror or e}", EXIT_INPUT)
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ToolError("input is not valid UTF-8 or GB18030 text", EXIT_INPUT)


def load_input(path: Path):
    """Return ('json', dict) or ('md', str) for an input path."""
    path = Path(path)
    if not path.is_file():
        raise ToolError(f"input file not found: {path.name}", EXIT_INPUT)
    text = read_text_file(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ToolError(f"invalid JSON: {e.msg} (line {e.lineno})", EXIT_INPUT)
        if not isinstance(data, dict):
            raise ToolError("JSON root must be an object", EXIT_INPUT)
        return "json", data
    if suffix in (".md", ".markdown", ".txt"):
        return "md", text
    raise ToolError(f"unsupported input type '{suffix}' (use .md or .json)", EXIT_INPUT)


# ---------------------------------------------------------------- path safety
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
_BAD_PREFIX = re.compile("[<>:\"/" + re.escape(chr(92)) + "|?*" + chr(0) + "-" + chr(31) + "]")


def check_prefix(prefix: str) -> str:
    if not prefix or _BAD_PREFIX.search(prefix) or prefix in (".", "..") \
            or prefix.endswith((" ", ".")) or prefix.upper().split(".")[0] in _RESERVED:
        raise ToolError("invalid --prefix: use a plain file name without path separators", EXIT_INPUT)
    if len(prefix) > 100:
        raise ToolError("--prefix too long (max 100)", EXIT_INPUT)
    return prefix


def prepare_output_dir(out_dir: Path, input_path: Path | None, dry_run: bool) -> Path:
    out_dir = Path(out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        raise ToolError("--output-dir exists and is not a directory", EXIT_INPUT)
    if "\x00" in str(out_dir):
        raise ToolError("invalid --output-dir", EXIT_INPUT)
    resolved = out_dir.resolve()
    if not dry_run:
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ToolError(f"cannot create output directory: {e.strerror or e}", EXIT_INPUT)
    return resolved


def pick_free_prefix(out_dir: Path, prefix: str, suffixes: list[str], force: bool) -> str:
    """Return a prefix for which none of the target files exist (unless force)."""
    if force:
        return prefix
    candidate, i = prefix, 0
    while any((out_dir / (candidate + s)).exists() for s in suffixes):
        i += 1
        candidate = f"{prefix}-{i}"
        if i > 9999:
            raise ToolError("could not find a free output name", EXIT_GENERATION)
    return candidate


def tmp_path_for(dest: Path) -> Path:
    fd, name = tempfile.mkstemp(prefix=".rd-", suffix=".tmp", dir=str(dest.parent))
    os.close(fd)
    return Path(name)


def commit_file(tmp: Path, dest: Path, force: bool) -> Path:
    """Move a validated temp file to dest without clobbering unless force."""
    if force:
        os.replace(tmp, dest)
        return dest
    try:
        os.link(tmp, dest)  # atomic, fails if dest exists
    except FileExistsError:
        raise ToolError(f"refusing to overwrite existing file: {dest.name}", EXIT_GENERATION)
    except OSError:
        if dest.exists():
            raise ToolError(f"refusing to overwrite existing file: {dest.name}", EXIT_GENERATION)
        os.rename(tmp, dest)
        return dest
    tmp.unlink(missing_ok=True)
    return dest


def write_atomic(dest: Path, data: bytes, force: bool, validator=None) -> Path:
    """Write bytes to a temp file, validate, then commit to dest. I/O problems become ToolError (exit 4)."""
    tmp = None
    try:
        tmp = tmp_path_for(dest)
        tmp.write_bytes(data)
        if validator:
            validator(tmp)
        return commit_file(tmp, dest, force)
    except ToolError:
        raise
    except OSError as e:  # e.g. target locked by another program, read-only folder, disk full
        raise ToolError(f"cannot write {dest.name}: {e.strerror or e}", EXIT_GENERATION)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def same_file(a: Path, b: Path) -> bool:
    """True if both paths denote the same file (case-insensitive on Windows, links resolved)."""
    a, b = Path(a), Path(b)
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def refuse_if_protected(target: Path, protected: list, what: str = "output") -> None:
    """Refuse to write `what` to `target` when it is one of the protected (input) files."""
    for p in protected:
        if p and same_file(target, Path(p)):
            raise ToolError(f"refusing to write {what} to '{Path(target).name}': that is an input file "
                            f"('{Path(p).name}'). Choose a different --output-dir/--prefix/--report.", EXIT_INPUT)


def report_unexpected(exc: Exception) -> int:
    """Last-resort handler: one-line redacted message, documented exit code, no traceback."""
    print(f"error: unexpected {type(exc).__name__}: {redact(str(exc))[:200]} "
          "(this is a bug; please report it with the command you ran)", file=sys.stderr)
    return EXIT_GENERATION


def ensure_parent_dir(path: Path) -> None:
    """Create the folder of a report file; a clear exit-2 error if that is impossible."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ToolError(f"cannot create the folder for '{Path(path).name}': {e.strerror or e}", EXIT_INPUT)


def write_json_report(path: Path, report: dict, force: bool) -> Path:
    data = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    dest = Path(path)
    ensure_parent_dir(dest)
    if not force and dest.exists():
        stem, i = dest.stem, 0
        while dest.exists():
            i += 1
            dest = dest.with_name(f"{stem}-{i}{dest.suffix}")
    return write_atomic(dest, data, force=force)
