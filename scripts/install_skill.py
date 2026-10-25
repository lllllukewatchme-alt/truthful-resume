#!/usr/bin/env python3
"""Install resume-design as a Claude Code or Codex skill. Preview with --dry-run; never overwrites silently."""
import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resume_design.common import setup_console  # noqa: E402
from resume_design import ROOT, __version__  # noqa: E402
from resume_design.common import EXIT_GENERATION, EXIT_INPUT, EXIT_OK, ToolError, redact  # noqa: E402

SKILL_NAME = "resume-design"
# target -> (adapter folder, relative install dir, scope)
TARGETS = {
    "claude-code-user": ("claude-code", Path(".claude/skills"), "user"),
    "claude-code-project": ("claude-code", Path(".claude/skills"), "project"),
    "codex-user": ("codex", Path(".agents/skills"), "user"),
    "codex-project": ("codex", Path(".agents/skills"), "project"),
}
COPY_DIRS = ["scripts", "resume_design", "templates", "references", "schemas", "core", "examples"]
COPY_FILES = ["VERSION", "README.md", "CHANGELOG.md"]


def build_parser():
    p = argparse.ArgumentParser(
        prog="install_skill.py",
        description="Install the skill (SKILL.md + engine) into a Claude Code or Codex skills folder. Claude Code: "
                    "~/.claude/skills (user) or <project>/.claude/skills. Codex: ~/.agents/skills (user) or "
                    "<project>/.agents/skills. If the destination exists the install stops unless --backup "
                    "(the old folder is renamed, never deleted).",
        epilog="Exit codes: 0 ok, 2 input/arg error, 4 install failed.")
    p.add_argument("--target", required=True, choices=sorted(TARGETS), help="where to install")
    p.add_argument("--project-dir", default="", help="project root for *-project targets (default: current dir)")
    p.add_argument("--home", default="", help="override the home directory (testing)")
    p.add_argument("--dry-run", action="store_true", help="show the plan; write nothing")
    p.add_argument("--backup", action="store_true", help="rename an existing install to <name>.bak-<timestamp> first")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def plan(args):
    adapter, rel, scope = TARGETS[args.target]
    base = Path(args.home) if args.home else Path.home()
    if scope == "project":
        base = Path(args.project_dir or ".").resolve()
        if not base.is_dir():
            raise ToolError("--project-dir is not a directory", EXIT_INPUT)
    dest = base / rel / SKILL_NAME
    skill_md = ROOT / "adapters" / adapter / "SKILL.md"
    if not skill_md.is_file():
        raise ToolError(f"adapter file missing: {skill_md.name}", EXIT_INPUT)
    files = [(skill_md, Path("SKILL.md"))]
    for d in COPY_DIRS:
        for f in sorted((ROOT / d).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                files.append((f, f.relative_to(ROOT)))
    for n in COPY_FILES:
        if (ROOT / n).is_file():
            files.append((ROOT / n, Path(n)))
    return dest, files


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    try:
        dest, files = plan(args)
        exists = dest.exists()
        print(f"target: {args.target}\ndestination: {dest}\nfiles: {len(files)}")
        if exists:
            print("destination EXISTS: " + ("will be renamed to a .bak-<timestamp> folder first" if args.backup
                                            else "install will stop (use --backup to keep the old copy)"))
        if args.dry_run:
            for _, rel in files[:12]:
                print(f"  would write {rel}")
            if len(files) > 12:
                print(f"  ... and {len(files) - 12} more")
            print("[dry-run] nothing written")
            return EXIT_OK
        if exists and not args.backup:
            raise ToolError(f"{dest} already exists; rerun with --backup or remove it yourself", EXIT_INPUT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        staging = dest.parent / f".{SKILL_NAME}.staging-{dt.datetime.now():%H%M%S%f}"
        try:
            for src, rel in files:
                out = staging / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, out)
            if exists:
                bak = dest.with_name(f"{SKILL_NAME}.bak-{dt.datetime.now():%Y%m%d%H%M%S}")
                dest.rename(bak)
                print(f"backup: {bak}")
            staging.rename(dest)
        except OSError as e:
            shutil.rmtree(staging, ignore_errors=True)  # only our own staging folder
            raise ToolError(f"install failed: {e.strerror or e}", EXIT_GENERATION)
        print(f"installed {SKILL_NAME} {__version__} -> {dest}")
        print("Restart/reload your agent session so the new skill is discovered.")
        return EXIT_OK
    except ToolError as e:
        print(f"error: {redact(str(e))}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
