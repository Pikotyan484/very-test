from __future__ import annotations

from collections import Counter

from ddgs import DDGS
import requests

from autopedia.config import Settings
from autopedia.models import SearchResult
from autopedia.utils import canonical_url, unique_preserve_order


class BraveSearchProvider:
    name = "brave"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        output: list[SearchResult] = []
        offset = 0
        rank = 1
        session = requests.Session()
        session.headers.update(
            {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            }
        )
        while len(output) < max_results:
            count = min(20, max_results - len(output))
            response = session.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": count, "offset": offset},
                timeout=30,
            )
            response.raise_for_status()
            items = response.json().get("web", {}).get("results", [])
            if not items:
                break
            for item in items:
                output.append(
                    SearchResult(
                        query=query,
                        title=item.get("title", "").strip(),
                        url=item.get("url", "").strip(),
                        snippet=item.get("description", "").strip(),
                        rank=rank,
                        provider=self.name,
                    )
                )
                rank += 1
            offset += len(items)
            if len(items) < count:
                break
        return output[:max_results]


class DuckDuckGoProvider:
    name = "ddgs"

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        output: list[SearchResult] = []
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            for rank, item in enumerate(results, start=1):
                output.append(
                    SearchResult(
                        query=query,
                        title=str(item.get("title", "")).strip(),
                        url=str(item.get("href", "")).strip(),
                        snippet=str(item.get("body", "")).strip(),
                        rank=rank,
                        provider=self.name,
                    )
                )
        return output


class SearxngProvider:
    name = "searxng"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        response = requests.get(
            f"{self.base_url}/search",
            params={"q": query, "format": "json", "language": "all"},
            headers={"User-Agent": "AutoPediaBot/1.0"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        output: list[SearchResult] = []
        for rank, item in enumerate(payload.get("results", [])[:max_results], start=1):
            output.append(
                SearchResult(
                    query=query,
                    title=str(item.get("title", "")).strip(),
                    url=str(item.get("url", "")).strip(),
                    snippet=str(item.get("content", "")).strip(),
                    rank=rank,
                    provider=self.name,
                )
            )
        return output


class SearchClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.providers = []
        for provider_name in unique_preserve_order(settings.search_providers):
            if provider_name == "searxng" and settings.searxng_url:
                self.providers.append(SearxngProvider(settings.searxng_url))
            elif provider_name == "brave" and settings.brave_api_key:
                self.providers.append(BraveSearchProvider(settings.brave_api_key))
            elif provider_name == "ddgs":
                self.providers.append(DuckDuckGoProvider())

        if not self.providers:
            self.providers.append(DuckDuckGoProvider())

    def search_many(self, queries: list[str], per_query: int) -> list[SearchResult]:
        combined: list[SearchResult] = []
        for query in queries:
            provider_hits: list[SearchResult] = []
            for provider in self.providers:
                try:
                    provider_hits.extend(provider.search(query, per_query))
                except Exception:
                    continue
                if len(provider_hits) >= per_query:
                    break
            combined.extend(provider_hits[:per_query])
        return self._dedupe(combined)

    def _dedupe(self, results: list[SearchResult]) -> list[SearchResult]:
        seen: set[str] = set()
        output: list[SearchResult] = []
        domain_counts: Counter[str] = Counter()
        backlog: list[SearchResult] = []

        for result in results:
            normalized_url = canonical_url(result.url)
            if not normalized_url or normalized_url in seen:
                continue
            result.url = normalized_url
            domain = normalized_url.split("/")[2]
            if domain_counts[domain] < 3:
                output.append(result)
                seen.add(normalized_url)
                domain_counts[domain] += 1
            else:
                backlog.append(result)

        for result in backlog:
            if result.url in seen:
                continue
            output.append(result)
            seen.add(result.url)
        return output
