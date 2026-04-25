import logging
import re
import urllib.parse

import httpx

logger = logging.getLogger(__name__)


class WebSearchClient:
    async def search(self, query: str, max_results: int = 3) -> list[str]:
        query = query.strip()
        if not query:
            return []
        encoded = urllib.parse.quote_plus(query)
        url = f"https://duckduckgo.com/html/?q={encoded}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                logger.warning("web search failed for query=%r: %s", query, exc)
                return []
        html = response.text
        return self._extract_snippets(html, max_results)

    def _extract_snippets(self, html: str, limit: int) -> list[str]:
        snippets: list[str] = []
        for match in re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', html):
            clean = re.sub(r"<.*?>", "", match)
            clean = re.sub(r"\s+", " ", clean).strip()
            if clean:
                snippets.append(clean)
            if len(snippets) >= limit:
                break
        return snippets


web_search_client = WebSearchClient()
