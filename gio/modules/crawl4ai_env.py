"""
Pin crawl4ai / Playwright / sqlite temp paths under gio/.crawl4ai.

Import this module before `crawl4ai` so sqlite and browser caches use writable dirs.
"""
import os


def bootstrap_crawl4ai_env() -> None:
    gio_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.join(gio_dir, ".crawl4ai")
    cache = os.path.join(root, "cache")
    data = os.path.join(root, "data")
    tmp = os.path.join(root, "tmp")
    for d in (root, cache, data, tmp):
        os.makedirs(d, exist_ok=True)

    os.environ.setdefault("CRAWL4AI_CACHE_DIR", cache)
    os.environ.setdefault("CRAWL4AI_DATA_DIR", data)
    os.environ.setdefault("XDG_CACHE_HOME", cache)
    os.environ.setdefault("XDG_DATA_HOME", data)
    # Do NOT set PLAYWRIGHT_BROWSERS_PATH here: crawl4ai needs a real Chromium install.
    # Use Playwright's default browser cache (~/.cache/ms-playwright) after `playwright install chromium`.
    os.environ.setdefault("TMPDIR", tmp)
    os.environ.setdefault("TEMP", tmp)
    os.environ.setdefault("TMP", tmp)
    os.environ.setdefault("SQLITE_TMPDIR", tmp)


bootstrap_crawl4ai_env()
