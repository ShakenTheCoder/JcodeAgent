"""
Web search & documentation reader for JCode.

Capabilities:
  1. web_search(query)  — Search the web via DuckDuckGo (no API key needed)
  2. fetch_page(url)    — Fetch and extract text content from a URL
  3. fetch_docs(url)    — Alias for fetch_page, focused on documentation

Requires internet_access permission to be granted by the user.
"""

from __future__ import annotations

import re
import json
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from rich.console import Console

console = Console()

# ── Global permission flag ─────────────────────────────────────────
_internet_allowed: bool = False


def set_internet_access(value: bool) -> None:
    """Set whether the agent may access the internet."""
    global _internet_allowed
    _internet_allowed = value


def is_internet_allowed() -> bool:
    """Check the current internet access setting."""
    return _internet_allowed


# ── Simple HTML text extractor ─────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Strip HTML tags and extract visible text."""

    _skip_tags = {"script", "style", "noscript", "svg", "path", "meta", "link", "head"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        raw = "\n".join(self._parts)
        # Collapse multiple blank lines
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _fetch_raw(url: str, timeout: int = 15) -> str:
    """Fetch raw HTML from a URL using only stdlib."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JCode/0.4; +https://github.com/ShakenTheCoder/JcodeAgent)",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


# ── Public API ─────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """
    Search the web using DuckDuckGo Lite (no API key required).

    Returns a list of dicts: [{"title": ..., "url": ..., "snippet": ...}, ...]
    """
    if not _internet_allowed:
        return [{"title": "Internet access not granted", "url": "", "snippet": ""}]

    try:
        encoded = urllib.parse.urlencode({"q": query})
        url = f"https://lite.duckduckgo.com/lite/?{encoded}"
        html = _fetch_raw(url, timeout=10)

        results: list[dict[str, str]] = []
        # Parse DDG Lite results — they use a table with class "result-link"
        link_pattern = re.compile(
            r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>',
            re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (href, title) in enumerate(links[:max_results]):
            title_clean = re.sub(r"<[^>]+>", "", title).strip()
            snippet_clean = ""
            if i < len(snippets):
                snippet_clean = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            results.append({
                "title": title_clean,
                "url": href,
                "snippet": snippet_clean,
            })

        if not results:
            # Fallback: try DuckDuckGo JSON API (limited but sometimes works)
            api_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
            raw = _fetch_raw(api_url, timeout=10)
            data = json.loads(raw)
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if "Text" in topic:
                    results.append({
                        "title": topic.get("Text", "")[:80],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", ""),
                    })

        return results or [{"title": "No results found", "url": "", "snippet": ""}]

    except Exception as e:
        return [{"title": f"Search failed: {e}", "url": "", "snippet": ""}]


def fetch_page(url: str, max_chars: int = 15000) -> str:
    """
    Fetch a URL and return extracted text content.
    Useful for reading documentation, READMEs, guides, etc.
    Strips HTML tags and returns clean text.
    """
    if not _internet_allowed:
        return "[Internet access not granted by user]"

    try:
        html = _fetch_raw(url, timeout=15)

        # If it looks like JSON, return it directly
        if url.endswith(".json") or html.strip().startswith("{"):
            return html[:max_chars]

        # If it looks like plain text / markdown
        if url.endswith((".md", ".txt", ".rst")) or "<html" not in html.lower()[:500]:
            return html[:max_chars]

        # Parse HTML to text
        extractor = _TextExtractor()
        extractor.feed(html)
        text = extractor.get_text()

        return text[:max_chars] if text else "(page returned no extractable text)"

    except Exception as e:
        return f"[Failed to fetch {url}: {e}]"


def fetch_docs(url: str, max_chars: int = 15000) -> str:
    """Alias for fetch_page — reads documentation from a URL."""
    return fetch_page(url, max_chars)


def search_and_summarize(query: str) -> str:
    """
    Search the web and fetch the top result's content.
    Returns a formatted string with search results + top page content.
    """
    if not _internet_allowed:
        return "[Internet access not granted by user]"

    results = web_search(query, max_results=3)
    parts = [f"Web search: {query}\n"]

    for i, r in enumerate(results, 1):
        parts.append(f"  {i}. {r['title']}")
        if r["url"]:
            parts.append(f"     {r['url']}")
        if r["snippet"]:
            parts.append(f"     {r['snippet'][:150]}")
        parts.append("")

    # Fetch the top result for full context
    top_url = next((r["url"] for r in results if r["url"]), None)
    if top_url:
        parts.append(f"--- Top result content ({top_url}) ---\n")
        content = fetch_page(top_url, max_chars=8000)
        parts.append(content)

    return "\n".join(parts)
