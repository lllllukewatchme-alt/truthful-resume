"""Environment detection (read-only; never installs or changes anything)."""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

CJK_FONT_HINTS = ["microsoft yahei", "simsun", "simhei", "dengxian", "noto sans cjk", "noto sans sc",
                  "noto serif sc", "source han", "pingfang", "heiti", "wenquanyi", "fangsong", "kaiti"]
# Test/diagnostic hook: RESUME_DESIGN_DISABLE_BACKENDS=word,libreoffice simulates a machine without them.
DISABLE_ENV = "RESUME_DESIGN_DISABLE_BACKENDS"


def _disabled() -> set[str]:
    return {x.strip().lower() for x in os.environ.get(DISABLE_ENV, "").split(",") if x.strip()}


def find_word() -> dict:
    info = {"name": "word", "available": False, "path": None, "version": None, "note": ""}
    if "word" in _disabled():
        info["note"] = f"disabled via {DISABLE_ENV}"
        return info
    if sys.platform != "win32":
        info["note"] = "Microsoft Word COM automation requires Windows"
        return info
    candidates = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            for sub in ("Microsoft Office/root/Office16", "Microsoft Office/Office16",
                        "Microsoft Office/root/Office15", "Microsoft Office/Office15"):
                candidates.append(Path(base) / sub / "WINWORD.EXE")
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE") as k:
                    candidates.insert(0, Path(winreg.QueryValue(k, None)))
            except OSError:
                pass
    except ImportError:
        pass
    for c in candidates:
        if c.is_file():
            info.update(available=True, path=str(c))
            break
    if info["available"]:
        try:
            ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                                 f"(Get-Item -LiteralPath $env:RD_WORD).VersionInfo.ProductVersion"],
                                capture_output=True, text=True, timeout=20,
                                env={**os.environ, "RD_WORD": info["path"]})
            info["version"] = ps.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
        info["note"] = "executable found; COM automation is verified only when an export is attempted"
    else:
        info["note"] = "WINWORD.EXE not found"
    return info


def find_libreoffice() -> dict:
    info = {"name": "libreoffice", "available": False, "path": None, "version": None, "note": ""}
    if "libreoffice" in _disabled():
        info["note"] = f"disabled via {DISABLE_ENV}"
        return info
    path = shutil.which("soffice") or shutil.which("libreoffice")
    if not path:
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base and (Path(base) / "LibreOffice/program/soffice.exe").is_file():
                path = str(Path(base) / "LibreOffice/program/soffice.exe")
                break
    if path:
        info.update(available=True, path=path)
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
            info["version"] = out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        info["note"] = "soffice not found on PATH or in standard install folders"
    return info


def find_pdftotext() -> dict:
    path = shutil.which("pdftotext")
    info = {"name": "pdftotext", "available": bool(path), "path": path, "version": None}
    if path:
        try:
            out = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=10)
            info["version"] = (out.stderr or out.stdout).strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    return info


def find_pdffonts() -> dict:
    path = shutil.which("pdffonts")
    return {"name": "pdffonts", "available": bool(path), "path": path}


def python_modules() -> dict:
    return {m: importlib.util.find_spec(m) is not None for m in ("docx", "pypdf", "fitz", "pytest")}


def installed_fonts() -> set[str] | None:
    """Lower-cased installed font names, or None when it cannot be determined."""
    names: set[str] = set()
    try:
        if sys.platform == "win32":
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as k:
                        i = 0
                        while True:
                            try:
                                names.add(winreg.EnumValue(k, i)[0].lower())
                                i += 1
                            except OSError:
                                break
                except OSError:
                    pass
        elif shutil.which("fc-list"):
            out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=30)
            names |= {x.strip().lower() for x in out.stdout.replace(",", "\n").splitlines() if x.strip()}
    except Exception:
        return None
    return names or None


def font_available(fonts: set[str] | None, name: str) -> bool | None:
    if fonts is None:
        return None
    n = name.lower()
    return any(n in f for f in fonts)


def cjk_fonts(fonts: set[str] | None) -> list[str] | None:
    if fonts is None:
        return None
    return sorted({h for h in CJK_FONT_HINTS if any(h in f for f in fonts)})


def pdf_backends() -> list[dict]:
    return [find_word(), find_libreoffice()]


def environment_report() -> dict:
    fonts = installed_fonts()
    backends = pdf_backends()
    usable = [b["name"] for b in backends if b["available"]]
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "arch": platform.machine(),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "python_modules": python_modules(),
        "pdf_backends": backends,
        "pdf_text_tools": {"pdftotext": find_pdftotext(), "pdffonts": find_pdffonts()},
        "fonts": {"detectable": fonts is not None, "cjk_fonts": cjk_fonts(fonts)},
        "capabilities": {
            "markdown": True,
            "docx": True,
            "pdf": bool(usable),
            "pdf_backends_usable": usable,
            "pdf_text_check": find_pdftotext()["available"] or python_modules()["pypdf"] or python_modules()["fitz"],
        },
    }
