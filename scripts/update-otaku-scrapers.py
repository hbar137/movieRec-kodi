#!/usr/bin/env python3
"""Vendor Otaku's anime-embed scrapers into our Kodi addon.

Pulls a fresh checkout of https://github.com/Goldenfreddy0703/Otaku and
copies a curated subset of files into
  plugin.video.movierec/resources/lib/otaku_scrapers/
while rewriting imports so they resolve inside our package.

Re-runnable: safe to invoke whenever upstream pushes scraper fixes
(typically when a streaming site changes its HTML / embed obfuscation).

Files marked "OURS" below are NOT overwritten — they are our thin
replacements for Otaku modules that are too tangled with Otaku's own
Kodi addon settings (control / database / utils). The script leaves
them alone.

Layout produced:
  otaku_scrapers/
    pages/      # one file per streaming provider
    ui/         # shared helpers (HTTP client, encryption, etc)
      jscrypto/, pyaes/   (Otaku's bundled crypto helpers)
    endpoints/  # malsync metadata lookup

License: vendored Otaku files remain GPL-3.0.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

OTAKU_REPO = "https://github.com/Goldenfreddy0703/Otaku.git"

# Files vendored verbatim from Otaku (path relative to plugin.video.otaku/
# resources/lib/). Each ends up at the same sub-path under
# otaku_scrapers/.
VENDORED_FILES = [
    # Per-site scrapers — match what the user has enabled in Otaku.
    "pages/animekai.py",
    "pages/animepahe.py",
    "pages/animixplay.py",
    "pages/aniwave.py",
    "pages/hianime.py",
    # Shared HTTP + crypto helpers used by the scrapers.
    "ui/BrowserBase.py",
    "ui/client.py",
    "ui/source_utils.py",
    "ui/megacloud_extractor.py",
    "ui/embed_extractor.py",
    "ui/jsunpack.py",
    "ui/jscrypto/__init__.py",
    "ui/jscrypto/jscrypto.py",
    "ui/jscrypto/pkcs7.py",
    "ui/jscrypto/pyaes.py",
    "ui/pyaes/__init__.py",
    "ui/pyaes/aes.py",
    "ui/pyaes/blockfeeder.py",
    "ui/pyaes/util.py",
    # MAL/AniList/Kitsu metadata lookup used by scrapers to map mal_id
    # → provider-specific slug/title.
    "endpoints/malsync.py",
]

# Empty package markers we create ourselves (not in Otaku tree).
INIT_FILES = [
    "__init__.py",
    "pages/__init__.py",
    "endpoints/__init__.py",
]
# ui/__init__.py is NOT created here — we ship our own (see "OURS"
# section below) so the package import doesn't accidentally trigger
# Otaku's eager module loads.

# OURS — files we manage by hand; the script never touches them.
# Listed only for documentation; absence from the copy loop is what
# matters.
OURS_DO_NOT_OVERWRITE = [
    "ui/__init__.py",
    "ui/control.py",
    "ui/database.py",
    "ui/utils.py",
]

DEST_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugin.video.movierec", "resources", "lib", "otaku_scrapers",
)


def rewrite_imports(src_text, rel_path):
    """Rewrite `from resources.lib.X[.Y...] import Z` so it resolves
    inside our otaku_scrapers package, using relative imports keyed
    off where the target file sits in the new tree.

    Mapping rules:
      file in pages/foo.py            : resources.lib.X → ..X     (parent package + X)
      file in endpoints/foo.py        : resources.lib.X → ..X
      file in ui/foo.py               : resources.lib.ui → .      (sibling pkg)
                                        resources.lib.ui.X → .X   (sibling module)
                                        resources.lib.endpoints[.X] → ..endpoints[.X]
      file in ui/sub/foo.py           : resources.lib.ui[.X] → ..[.X]
                                        resources.lib.endpoints[.X] → ...endpoints[.X]
    """
    parts = rel_path.split("/")
    pkg = parts[0]  # 'pages' | 'ui' | 'endpoints'
    depth = len(parts) - 1  # how nested inside otaku_scrapers/

    # Number of leading dots needed to step from the current file's
    # package up to otaku_scrapers/. Then we append the target subpath.
    # depth=1 (pages/x.py): one step up → ".." → "from ..ui ..."
    # depth=2 (ui/sub/x.py): two steps up → "..." → "from ...ui ..."
    up = "." * (depth + 1)  # one extra for the implicit leading dot
    # That makes:
    #   ui/x.py    (depth 1) → up = ".."  → "from ..ui" → wrong, we want "from . for sibling ui"
    #   pages/x.py (depth 1) → up = ".."  → "from ..ui" → correct

    def target_prefix(target_pkg):
        """Prefix string for an import targeting another otaku_scrapers
        subpackage. e.g. for ui/x.py importing ui/y, returns '.' for
        a sibling import; for pages/x.py importing ui/y, returns '..ui'.
        """
        if pkg == target_pkg:
            # Sibling: just step into the same package using leading dots.
            #   ui/foo.py: depth=1, sibling ui/bar → "from . import bar"   (1 dot)
            #   ui/sub/foo.py: depth=2, sibling ui/sub/bar → "from . import bar"
            # Stepping out then back IN to the same package is unnecessary.
            return "." * (depth - 0)
        # Cross-package: step up (depth dots) and then add ".target".
        # pages/foo.py (depth=1) → ui: ".." + "ui" = "..ui"
        # ui/foo.py (depth=1) → endpoints: ".." + "endpoints" = "..endpoints"
        # ui/sub/foo.py (depth=2) → endpoints: "..." + "endpoints" = "...endpoints"
        return ("." * (depth + 1)) + target_pkg

    def repl(m):
        # m.group(1) = the X[.Y...] after "resources.lib."
        # m.group(2) = the " import ..." tail
        target = m.group(1)
        rest = m.group(2)
        seg = target.split(".", 1)
        target_pkg = seg[0]                # 'ui' | 'endpoints' | (others)
        target_sub = seg[1] if len(seg) > 1 else ""

        if target_pkg not in ("ui", "endpoints"):
            # Unknown target (e.g. resources.lib.Main) — leave alone so
            # the broken import is visible and reviewable, rather than
            # silently mis-routed.
            return m.group(0)

        prefix = target_prefix(target_pkg)
        if target_sub:
            # When prefix is pure dots (sibling case, no pkg name), the
            # sub-name attaches directly: "." + "pyaes" → ".pyaes". When
            # prefix already has a pkg name, we need a dot separator:
            # "..ui" + "." + "megacloud" → "..ui.megacloud".
            sep = "" if prefix.endswith(".") else "."
            return f"from {prefix}{sep}{target_sub}{rest}"
        else:
            return f"from {prefix}{rest}"

    return re.sub(
        r"from\s+resources\.lib\.((?:ui|endpoints)(?:\.[\w.]+)?)(\s+import\s+.+)",
        repl, src_text,
    )


def main():
    with tempfile.TemporaryDirectory() as tmp:
        otaku_dir = os.path.join(tmp, "otaku")
        print(f"cloning {OTAKU_REPO} → {otaku_dir}")
        subprocess.run(
            ["git", "clone", "--depth", "1", OTAKU_REPO, otaku_dir],
            check=True, capture_output=True,
        )
        sha = subprocess.check_output(
            ["git", "-C", otaku_dir, "rev-parse", "HEAD"], text=True,
        ).strip()
        print(f"upstream HEAD: {sha[:12]}")

        src_root = os.path.join(otaku_dir, "plugin.video.otaku", "resources", "lib")

        # Verbatim copies + import rewrites.
        for rel in VENDORED_FILES:
            src = os.path.join(src_root, rel)
            dst = os.path.join(DEST_ROOT, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, "r", encoding="utf-8") as fh:
                text = fh.read()
            text = rewrite_imports(text, rel)
            # Prepend a header so future readers know it's vendored.
            header = (
                f"# Vendored from {OTAKU_REPO} @ {sha[:12]}\n"
                f"#   plugin.video.otaku/resources/lib/{rel}\n"
                f"# Regenerate via scripts/update-otaku-scrapers.py\n"
                f"# License: GPL-3.0 (Otaku).\n"
            )
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(header + text)
            print(f"  vendored {rel}")

        # Empty __init__.py markers (ones we own).
        for rel in INIT_FILES:
            dst = os.path.join(DEST_ROOT, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write("")
                print(f"  created {rel}")

        # Write the upstream pin so we can show it in logs / debug.
        pin_path = os.path.join(DEST_ROOT, "_otaku_sha.txt")
        with open(pin_path, "w", encoding="utf-8") as fh:
            fh.write(sha + "\n")

        print(f"done. otaku sha pinned at {pin_path}")


if __name__ == "__main__":
    main()
