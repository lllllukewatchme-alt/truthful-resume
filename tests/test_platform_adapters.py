"""Static checks of adapter files. These prove the files are well-formed and consistent with the engine;
they do NOT prove that Claude Code, Codex, DeepSeek or Doubao actually load/behave (see core/platform-capabilities.md)."""
import importlib.util
import re
import unittest
from pathlib import Path

from helpers import ROOT, SCRIPTS

SCRIPT_NAMES = ["generate_resume", "validate_resume", "export_pdf", "inspect_environment", "match_jd", "install_skill"]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "frontmatter must start on line 1"
    fm, key = {}, None
    for line in m.group(1).splitlines():
        if re.match(r"^[A-Za-z_-]+:", line):
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip()
        elif key and line.startswith(" "):
            fm[key] += " " + line.strip()
    return fm, text[m.end():]


def option_strings(script):
    parser = load_script(script).build_parser()
    return {o for a in parser._actions for o in a.option_strings if o.startswith("--")}


class SkillFiles(unittest.TestCase):
    PATHS = {"claude-code": ROOT / "adapters/claude-code/SKILL.md", "codex": ROOT / "adapters/codex/SKILL.md"}

    def test_frontmatter_valid(self):
        for plat, p in self.PATHS.items():
            fm, body = frontmatter(p.read_text(encoding="utf-8"))
            self.assertEqual(fm["name"], "resume-design", plat)
            self.assertRegex(fm["name"], r"^[a-z0-9-]{1,64}$")
            self.assertTrue(fm["description"], plat)
            self.assertLessEqual(len(fm["description"]), 1536, plat)
            self.assertNotRegex(fm["description"], r"[<>]")
            self.assertRegex(fm["description"].lower(), r"(do not|don't)", f"{plat}: description must state non-triggers")
            self.assertLess(len(body.splitlines()), 150, f"{plat}: keep SKILL.md lean")

    def test_required_sections(self):
        needed = ["When this applies", "Intent", "Collecting information", "Truthfulness", "Template choice",
                  "Generate", "Check", "Errors", "Status words", "Privacy"]
        for plat, p in self.PATHS.items():
            heads = "\n".join(re.findall(r"^##+ .*$", p.read_text(encoding="utf-8"), re.M))
            for n in needed:
                self.assertIn(n, heads, f"{plat} missing section {n}")
            self.assertIn("Load on demand", heads.replace("Load on demand (read only when needed)", "Load on demand"))

    def test_referenced_files_exist(self):
        for plat, p in self.PATHS.items():
            text = p.read_text(encoding="utf-8")
            refs = set(re.findall(r"`((?:core|references)/[\w./-]+\.md)`", text))
            self.assertTrue(refs)
            for r in refs:
                self.assertTrue((ROOT / r).is_file(), f"{plat}: {r} missing")
            for s in set(re.findall(r"scripts/(\w+\.py)", text)):
                self.assertTrue((SCRIPTS / s).is_file(), f"{plat}: scripts/{s} missing")

    def test_commands_use_real_flags(self):
        for plat, p in self.PATHS.items():
            for line in p.read_text(encoding="utf-8").splitlines():
                m = re.search(r"scripts/(\w+)\.py(.*)", line)
                if m and m.group(1) in SCRIPT_NAMES and "`" not in m.group(2)[:1]:
                    valid = option_strings(m.group(1)) | {"--help"}
                    for flag in re.findall(r"(--[a-z][a-z-]+)", m.group(2)):
                        self.assertIn(flag, valid, f"{plat}: {flag} not accepted by {m.group(1)}.py")

    def test_flags_listed_in_options_line_exist(self):
        gen = option_strings("generate_resume")
        for plat, p in self.PATHS.items():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith("Options:"):
                    for flag in re.findall(r"`(--[a-z-]+)", line):
                        self.assertIn(flag, gen, f"{plat}: {flag}")

    def test_platform_specific_paths(self):
        cc = self.PATHS["claude-code"].read_text(encoding="utf-8")
        cx = self.PATHS["codex"].read_text(encoding="utf-8")
        self.assertIn("${CLAUDE_SKILL_DIR}", cc)
        self.assertNotIn("${CLAUDE_SKILL_DIR}", cx)
        self.assertIn(".agents/skills", cx)
        self.assertNotIn(".claude/skills", cx)

    def test_agents_md_example(self):
        t = (ROOT / "adapters/codex/AGENTS.md.example").read_text(encoding="utf-8")
        for k in ("{{MISSING:", "--force", "Never upload", "ai_suggested"):
            self.assertIn(k, t)


class PromptFiles(unittest.TestCase):
    PROMPTS = {n: ROOT / f"adapters/{n}/PROMPT.md" for n in ("deepseek", "doubao", "generic")}

    def test_prompts_have_core_rules(self):
        for n, p in self.PROMPTS.items():
            t = p.read_text(encoding="utf-8")
            self.assertIn("{{MISSING:", t, n)
            self.assertIn("ai_suggested", t, n)
            self.assertIn("generate_resume.py", t, n)
            self.assertIn("ready_to_submit", t, n)
            self.assertRegex(t, r"cannot|不能", n)          # capability disclaimer
            self.assertRegex(t, r"untested|未实测|尚未", n)    # honest status
            for flag in re.findall(r"(--[a-z][a-z-]+)", t):
                self.assertIn(flag, option_strings("generate_resume") | option_strings("validate_resume"), f"{n}: {flag}")

    def test_prompt_json_skeleton_matches_schema(self):
        import json
        from resume_design.schema_check import validate_schema
        for n, p in self.PROMPTS.items():
            blocks = re.findall(r"```json\n(.*?)\n```", p.read_text(encoding="utf-8"), re.S)
            self.assertTrue(blocks, n)
            sk = blocks[0].replace("YYYY-MM 或 present", "2020-01").replace("YYYY-MM or present", "2020-01")
            data = json.loads(sk)
            data["basics"]["name"] = "X"
            self.assertEqual(validate_schema(data), [], n)


class CapabilityMatrix(unittest.TestCase):
    def setUp(self):
        self.t = (ROOT / "core/platform-capabilities.md").read_text(encoding="utf-8")

    def rows(self):
        return {re.split(r"\s*\|\s*", l.strip("| "))[0]: l for l in self.t.splitlines() if l.startswith("| ")}

    def test_untested_platforms_not_claimed_tested(self):
        rows = self.rows()
        for name in ("Claude Code", "OpenAI Codex", "DeepSeek (web/app/API)", "Doubao (豆包)", "Other LLMs"):
            r = rows[name]
            self.assertNotIn("**tested**", r, name)
            self.assertTrue(re.search(r"spec-based|manual", r), name)
            self.assertRegex(r, r"not invoked|untested|未实测", name)

    def test_vocabulary_defined(self):
        for w in ("tested", "spec-based", "manual", "unsupported"):
            self.assertIn(w, self.t)

    def test_install_paths_documented_match_installer(self):
        inst = load_script("install_skill")
        for target, (adapter, rel, scope) in inst.TARGETS.items():
            self.assertIn(rel.as_posix(), self.t if scope == "user" else self.t + (ROOT / "README.md").read_text(encoding="utf-8") + (ROOT / "docs/USAGE.md").read_text(encoding="utf-8"))


class RepoConsistency(unittest.TestCase):
    def test_single_placeholder_standard(self):
        offenders = []
        for p in ROOT.rglob("*"):
            if p.is_file() and p.suffix in (".md", ".py", ".json", ".example") and "reports" not in p.parts and "__pycache__" not in p.parts \
                    and ".git" not in p.parts and p.name != "test_platform_adapters.py":
                if "[[TODO:" in p.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(p.name)
        self.assertEqual(offenders, [], "only {{MISSING:field}} is allowed")

    def test_version_files_agree(self):
        v = (ROOT / "VERSION").read_text().strip()
        self.assertIn(f"version = \"{v}\"", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn(f"## {v}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertIn(f'version: "{v}"', (ROOT / "adapters/claude-code/SKILL.md").read_text(encoding="utf-8"))

    def test_readme_matches_help(self):
        # README is the short beginner page; the complete option reference lives in docs/USAGE.md
        readme = (ROOT / "README.md").read_text(encoding="utf-8") + "\n" + (ROOT / "docs/USAGE.md").read_text(encoding="utf-8")
        for s in SCRIPT_NAMES:
            self.assertIn(f"scripts/{s}.py", readme, f"README never mentions {s}.py")
            for opt in option_strings(s) - {"--help", "--version"}:
                self.assertIn(opt, readme, f"README lacks {s} option {opt}")
        # every flag used in README command lines is real for the script it is used with
        for line in readme.splitlines():
            m = re.search(r"scripts[/\\](\w+)\.py(.*)", line)
            if m and m.group(1) in SCRIPT_NAMES:
                for flag in re.findall(r"(--[a-z][a-z-]+)", m.group(2)):
                    self.assertIn(flag, option_strings(m.group(1)) | {"--help"}, f"README: {flag} for {m.group(1)}")

    def test_all_scripts_have_help(self):
        import subprocess, sys
        for s in SCRIPT_NAMES:
            p = subprocess.run([sys.executable, str(SCRIPTS / f"{s}.py"), "--help"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            self.assertEqual(p.returncode, 0, s)
            self.assertIn("usage:", p.stdout)

    def test_content_and_style_templates_pair_up(self):
        styles = {p.stem for p in (ROOT / "templates/styles").glob("*.json")}
        contents = {p.stem for p in (ROOT / "templates/content").glob("*.md")}
        self.assertTrue(styles <= contents)
        self.assertEqual(styles, {"ats-clean", "technical", "management", "modern-business", "creative", "harvard", "banner",
                                  "sidebar-dark", "timeline", "date-left", "developer-mono"})
        import json
        for s in styles:
            st = json.loads((ROOT / f"templates/styles/{s}.json").read_text(encoding="utf-8"))
            for k in ("page", "fonts", "spacing", "colors", "heading", "layout", "header_footer", "pagination", "ats"):
                self.assertIn(k, st, f"{s} lacks {k}")


if __name__ == "__main__":
    unittest.main()
