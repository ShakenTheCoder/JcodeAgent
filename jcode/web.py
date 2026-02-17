"""
Web search & documentation reader for JCode.

Capabilities:
  1. web_search(query)       — Search the web via DuckDuckGo (no API key needed)
  2. fetch_page(url)         — Fetch and extract text content from a URL
  3. fetch_docs(url)         — Alias for fetch_page, focused on documentation
  4. search_and_summarize()  — Search + fetch top result
  5. research_task()         — Full research pipeline for heavy tasks (v0.9.0)
  6. fetch_tech_docs()       — Fetch official docs for specific technologies

Requires internet_access permission to be granted by the user.

v0.9.0 — Research pipeline for heavy tasks: multi-query search,
         tech-specific documentation fetching, parallel result gathering.
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


# ═══════════════════════════════════════════════════════════════════
# Research Pipeline — for heavy tasks (v0.9.0)
# ═══════════════════════════════════════════════════════════════════

# Official documentation URLs for common technologies
_TECH_DOCS: dict[str, list[str]] = {
    "react": [
        "https://react.dev/learn",
    ],
    "next": [
        "https://nextjs.org/docs/getting-started/installation",
    ],
    "nextjs": [
        "https://nextjs.org/docs/getting-started/installation",
    ],
    "vue": [
        "https://vuejs.org/guide/quick-start.html",
    ],
    "svelte": [
        "https://svelte.dev/docs/introduction",
    ],
    "fastapi": [
        "https://fastapi.tiangolo.com/tutorial/first-steps/",
    ],
    "flask": [
        "https://flask.palletsprojects.com/en/stable/quickstart/",
    ],
    "django": [
        "https://docs.djangoproject.com/en/5.1/intro/tutorial01/",
    ],
    "express": [
        "https://expressjs.com/en/starter/hello-world.html",
    ],
    "tailwind": [
        "https://tailwindcss.com/docs/installation",
    ],
    "prisma": [
        "https://www.prisma.io/docs/getting-started/quickstart",
    ],
    "mongodb": [
        "https://www.mongodb.com/docs/manual/tutorial/getting-started/",
    ],
    "postgres": [
        "https://www.postgresql.org/docs/current/tutorial.html",
    ],
    "redis": [
        "https://redis.io/docs/latest/get-started/",
    ],
    "docker": [
        "https://docs.docker.com/get-started/",
    ],
    "stripe": [
        "https://docs.stripe.com/get-started",
    ],
    "socket.io": [
        "https://socket.io/docs/v4/tutorial/introduction",
    ],
    "websocket": [
        "https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API",
    ],
    "graphql": [
        "https://graphql.org/learn/",
    ],
}


def _extract_technologies(prompt: str) -> list[str]:
    """Extract technology keywords from a prompt for targeted doc lookup."""
    lower = prompt.lower()
    found: list[str] = []
    for tech in _TECH_DOCS:
        if tech in lower:
            found.append(tech)
    return found


def fetch_tech_docs(
    technologies: list[str],
    max_per_tech: int = 1,
    max_chars: int = 5000,
) -> dict[str, str]:
    """Fetch official documentation for specific technologies.

    Returns a dict of {technology: doc_content}.
    """
    if not _internet_allowed:
        return {}

    docs: dict[str, str] = {}
    for tech in technologies:
        urls = _TECH_DOCS.get(tech, [])
        for url in urls[:max_per_tech]:
            try:
                content = fetch_page(url, max_chars=max_chars)
                if content and not content.startswith("[Failed"):
                    docs[tech] = content
                    break
            except Exception:
                continue

    return docs


def research_task(
    prompt: str,
    max_search_queries: int = 3,
    max_doc_pages: int = 3,
) -> str:
    """
    Full research pipeline for heavy tasks.

    Steps:
    1. Extract technologies from the prompt
    2. Generate search queries based on the task
    3. Search the web for each query
    4. Fetch official docs for detected technologies
    5. Compile all findings into a research brief

    Returns a formatted research brief string.
    """
    if not _internet_allowed:
        return "[Internet access not granted — skipping research]"

    console.print("  [dim]🔍 Researching task...[/dim]")
    parts: list[str] = []

    # 1. Extract technologies
    technologies = _extract_technologies(prompt)
    if technologies:
        console.print(f"  [dim]   Technologies detected: {', '.join(technologies)}[/dim]")

    # 2. Generate search queries
    queries = _generate_search_queries(prompt, technologies)

    # 3. Web search for each query
    all_results: list[dict[str, str]] = []
    for i, query in enumerate(queries[:max_search_queries]):
        console.print(f"  [dim]   Searching: {query}[/dim]")
        results = web_search(query, max_results=3)
        all_results.extend(results)

    # Format search results
    if all_results:
        parts.append("## Web Search Results\n")
        seen_urls: set[str] = set()
        for r in all_results:
            if r["url"] and r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                parts.append(f"- **{r['title']}**")
                parts.append(f"  {r['snippet'][:200]}")
                parts.append(f"  URL: {r['url']}\n")

    # 4. Fetch top search result pages (up to max_doc_pages)
    fetched = 0
    for r in all_results:
        if fetched >= max_doc_pages:
            break
        url = r.get("url", "")
        if not url:
            continue
        console.print(f"  [dim]   Reading: {url[:60]}...[/dim]")
        content = fetch_page(url, max_chars=4000)
        if content and not content.startswith("[Failed"):
            parts.append(f"\n## Page: {r['title']}\n")
            parts.append(content[:4000])
            fetched += 1

    # 5. Fetch official docs
    if technologies:
        console.print(f"  [dim]   Fetching official docs...[/dim]")
        tech_docs = fetch_tech_docs(technologies, max_chars=4000)
        for tech, content in tech_docs.items():
            parts.append(f"\n## Official Docs: {tech}\n")
            parts.append(content[:4000])

    research_text = "\n".join(parts)

    if not research_text.strip():
        return "[No relevant research found]"

    # Truncate total research to avoid overwhelming the context
    max_total = 20000
    if len(research_text) > max_total:
        research_text = research_text[:max_total] + "\n\n[... truncated ...]"

    console.print(f"  [dim]   ✓ Research complete ({len(research_text)} chars)[/dim]")
    return research_text


def _generate_search_queries(prompt: str, technologies: list[str]) -> list[str]:
    """Generate targeted search queries from the task prompt."""
    queries: list[str] = []

    # Main task query
    # Take first 80 chars of the prompt as the primary query
    primary = prompt[:80].strip()
    if primary:
        queries.append(f"{primary} tutorial implementation")

    # Technology-specific queries
    for tech in technologies[:2]:
        queries.append(f"{tech} best practices 2025 implementation guide")

    # If there are specific patterns in the prompt
    lower = prompt.lower()
    if "auth" in lower:
        queries.append("authentication implementation best practices 2025")
    if "database" in lower or "postgres" in lower or "mongo" in lower:
        queries.append("database schema design best practices")
    if "api" in lower and "rest" in lower:
        queries.append("REST API design best practices")
    if "websocket" in lower or "real-time" in lower:
        queries.append("websocket implementation best practices")
    if "docker" in lower:
        queries.append("Dockerfile best practices multi-stage build")

    return queries[:5]  # Cap at 5 queries
