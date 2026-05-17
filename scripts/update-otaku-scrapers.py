#!/usr/bin/env python3
"""Vendor Otaku's anime-embed scrapers + ALL their dependencies into
our Kodi addon, line-by-line.

Output goes to plugin.video.movierec/resources/lib/otaku_scrapers/.
Everything is verbatim from upstream Otaku except:
  - import paths are rewritten to use relative imports inside the
    otaku_scrapers package (`from resources.lib.X` → `from ..X`)
  - the addon id in control.py is swapped from 'plugin.video.otaku'
    to 'plugin.video.movierec' so Otaku's settings/profile/database
    helpers read OUR addon's state, not a non-existent Otaku install

No thin replacements. No monkey-patches. If something breaks the right
fix is to vendor more of Otaku, not paper over it on our side.

Re-runnable: safe to invoke whenever upstream pushes scraper fixes.

License: vendored Otaku files remain GPL-3.0.
"""
import os
import re
import subprocess
import sys
import tempfile

OTAKU_REPO = "https://github.com/Goldenfreddy0703/Otaku.git"

# Files vendored from Otaku, paths relative to plugin.video.otaku/
# resources/lib/. Each lands at the same sub-path under
# otaku_scrapers/. Everything Otaku's scrapers and their transitive
# deps need — control, database, utils, client are ALL real Otaku.
VENDORED_FILES = [
    # Per-site scrapers — match what the user has enabled in Otaku.
    "pages/animekai.py",
    "pages/animepahe.py",
    "pages/animixplay.py",
    "pages/aniwave.py",
    "pages/hianime.py",

    # Full ui/ — real Otaku code, no thin replacements.
    "ui/BrowserBase.py",
    "ui/client.py",
    "ui/control.py",
    "ui/database.py",
    "ui/utils.py",
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

    # Endpoints — malsync (used by all scrapers for slug/title lookup).
    "endpoints/malsync.py",
]

# Empty package markers — we own these so they don't get overwritten.
INIT_FILES = [
    "__init__.py",
    "pages/__init__.py",
    "ui/__init__.py",
    "endpoints/__init__.py",
]

DEST_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugin.video.movierec", "resources", "lib", "otaku_scrapers",
)


def rewrite_imports(src_text, rel_path):
    """Rewrite `from resources.lib.X[.Y...] import Z` to use relative
    imports anchored inside our otaku_scrapers package.

    Mapping rules:
      pages/foo.py        : resources.lib.X → ..X    (parent + X)
      endpoints/foo.py    : resources.lib.X → ..X
      ui/foo.py           : resources.lib.ui → .     (sibling pkg)
                            resources.lib.ui.X → .X  (sibling module)
                            resources.lib.endpoints[.X] → ..endpoints[.X]
      ui/sub/foo.py       : resources.lib.ui[.X] → ..[.X]
                            resources.lib.endpoints[.X] → ...endpoints[.X]
    """
    parts = rel_path.split("/")
    pkg = parts[0]  # 'pages' | 'ui' | 'endpoints'
    depth = len(parts) - 1  # how nested inside otaku_scrapers/

    def target_prefix(target_pkg):
        if pkg == target_pkg:
            # Sibling: stay in the same package — leading dots only.
            return "." * depth
        # Cross-package: step up (depth dots) then add the target pkg name.
        return ("." * (depth + 1)) + target_pkg

    def repl(m):
        target = m.group(1)
        rest = m.group(2)
        seg = target.split(".", 1)
        target_pkg = seg[0]
        target_sub = seg[1] if len(seg) > 1 else ""

        if target_pkg not in ("ui", "endpoints"):
            # Unknown target (e.g. resources.lib.Main) — leave alone so
            # the broken import is visible rather than mis-routed.
            return m.group(0)

        prefix = target_prefix(target_pkg)
        if target_sub:
            sep = "" if prefix.endswith(".") else "."
            return f"from {prefix}{sep}{target_sub}{rest}"
        return f"from {prefix}{rest}"

    return re.sub(
        r"from\s+resources\.lib\.((?:ui|endpoints)(?:\.[\w.]+)?)(\s+import\s+.+)",
        repl, src_text,
    )


def post_process(src_text, rel_path):
    """Per-file tweaks that go beyond import rewriting.

    Currently just one: control.py reads addon state via
    xbmcaddon.Addon('plugin.video.otaku'). Swap to our id so it reads
    OUR addon's settings/profile/database — otherwise it errors out
    when Otaku isn't installed (which is the whole point of vendoring).
    """
    if rel_path == "ui/control.py":
        src_text = src_text.replace("'plugin.video.otaku'", "'plugin.video.movierec'")
        src_text = src_text.replace('"plugin.video.otaku"', '"plugin.video.movierec"')
    return src_text


CONTEXT_ADDON_DEST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "context.otaku",
)


def vendor_context_addon(otaku_dir, sha):
    """Copy Otaku's sibling context.otaku addon into our repo as a
    standalone Kodi addon. plugin.video.movierec's vendored control.py
    references context.otaku for icon/genre asset paths + info.db, so
    we ship it alongside in our Kodi repo.
    """
    import shutil

    src = os.path.join(otaku_dir, "context.otaku")
    if not os.path.isdir(src):
        print(f"  WARN: {src} missing in upstream — skipping context.otaku vendor")
        return
    if os.path.isdir(CONTEXT_ADDON_DEST):
        shutil.rmtree(CONTEXT_ADDON_DEST)
    shutil.copytree(src, CONTEXT_ADDON_DEST)
    # Pin the upstream sha so users can verify what they have.
    with open(os.path.join(CONTEXT_ADDON_DEST, "_otaku_sha.txt"), "w") as fh:
        fh.write(sha + "\n")
    print(f"  vendored context.otaku → {CONTEXT_ADDON_DEST}")


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

        for rel in VENDORED_FILES:
            src = os.path.join(src_root, rel)
            dst = os.path.join(DEST_ROOT, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, "r", encoding="utf-8") as fh:
                text = fh.read()
            text = rewrite_imports(text, rel)
            text = post_process(text, rel)
            header = (
                f"# Vendored from {OTAKU_REPO} @ {sha[:12]}\n"
                f"#   plugin.video.otaku/resources/lib/{rel}\n"
                f"# Regenerate via scripts/update-otaku-scrapers.py\n"
                f"# License: GPL-3.0 (Otaku).\n"
            )
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(header + text)
            print(f"  vendored {rel}")

        # Empty __init__.py markers (only if missing — never overwrite).
        for rel in INIT_FILES:
            dst = os.path.join(DEST_ROOT, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write("")
                print(f"  created {rel}")

        pin_path = os.path.join(DEST_ROOT, "_otaku_sha.txt")
        with open(pin_path, "w", encoding="utf-8") as fh:
            fh.write(sha + "\n")
        print(f"done. otaku sha pinned at {pin_path}")

        # Also vendor the sibling context.otaku addon — our vendored
        # control.py references it at module load time.
        vendor_context_addon(otaku_dir, sha)


if __name__ == "__main__":
    main()
