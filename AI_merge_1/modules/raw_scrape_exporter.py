import hashlib
import os
from datetime import datetime


def _safe_slug(url: str) -> str:
    h = hashlib.md5((url or "").encode("utf-8")).hexdigest()[:10]
    return h


def write_raw_scrape_markdown(
    *,
    url: str,
    parent_url: str | None,
    url_type: str,
    scraped_text: str,
    out_dir: str,
) -> str:
    """
    Write the raw scraped text (pre-LLM) to a markdown file for troubleshooting.
    Returns the written file path.
    """
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    slug = _safe_slug(url)
    filename = f"{ts}_{slug}.md"
    path = os.path.join(out_dir, filename)

    header_lines = [
        f"# Raw scrape",
        f"- **URL**: {url}",
        f"- **Parent URL**: {parent_url or ''}",
        f"- **Type**: {url_type}",
        "",
        "---",
        "",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines))
        f.write(scraped_text or "")
        f.write("\n")

    return path

