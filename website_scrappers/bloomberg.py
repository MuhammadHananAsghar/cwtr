import json
import asyncio
import aiohttp
import requests
from typing import List, Dict, Any
from datetime import datetime
from colorama import Fore, Style, init
from threading import Lock
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

init(autoreset=True)

print_lock = Lock()


def safe_print(message: str):
    with print_lock:
        print(message)


class BloombergScraper:
    def __init__(self, max_concurrent: int = 5):
        ua = UserAgent()
        self.headers = {
            "User-Agent": ua.random,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.bloomberg.com/crypto",
            "Connection": "keep-alive",
        }
        self.base_url = "https://www.bloomberg.com/lineup-next/api/paginate"
        self.source_name = "Bloomberg"
        self.source_url = "https://www.bloomberg.com"
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, "scraper"):
            await self.scraper.close()

    async def get_article_content(
        self, session: aiohttp.ClientSession, slug: str
    ) -> str:
        try:
            url = f"https://www.bloomberg.com/news/articles/{slug}"
            async with session.get(url) as response:
                response.raise_for_status()
                html = await response.text()

            soup = BeautifulSoup(html, "html.parser")
            content_div = soup.find("div", class_=lambda x: x and "body-content" in x)

            if not content_div:
                return ""

            paragraphs = []
            for p in content_div.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)

            content = " ".join(paragraphs)
            content = " ".join(content.split())

            safe_print(
                f"{Fore.GREEN}✓ Successfully fetched content for {slug}{Style.RESET_ALL}"
            )
            return content

        except Exception as e:
            safe_print(
                f"{Fore.RED}✗ Error fetching content for {slug}: {e}{Style.RESET_ALL}"
            )
            return ""

    async def format_article(
        self, session: aiohttp.ClientSession, article: Dict[str, Any]
    ) -> Dict[str, Any]:
        credits = article.get("credits", [])
        author_name = credits[0].get("name") if credits else None

        # Get category from either label or eyebrow
        category = None
        if article.get("label"):
            category = article.get("label")
        elif article.get("eyebrow", {}).get("text"):
            category = article.get("eyebrow", {}).get("text")

        slug = article.get("slug", "")
        content = await self.get_article_content(session, slug) if slug else ""
        # If no content, try to get summary
        if not content or content == "":
            content = article.get("summary", "")

        # Get tags from eyebrow
        eyebrow = article.get("eyebrow", {})
        tags = [eyebrow.get("text")] if eyebrow and eyebrow.get("text") else []

        # Get image URL from either image or lede
        image_url = ""
        image = article.get("image", {})
        lede = article.get("lede", {})
        if image:
            image_url = image.get("baseUrl", "")
        elif lede:
            image_url = lede.get("baseUrl", "")

        return {
            "id": article.get("id", ""),
            "slug": slug,
            "title": article.get("headline", ""),
            "content": content,
            "publishedAt": article.get("publishedAt", ""),
            "authorName": author_name,
            "category": category,
            "sourceName": self.source_name,
            "sourceUrl": self.source_url,
            "imageUrl": image_url,
            "articleUrl": f"{self.source_url}/news/articles/{slug}",
            "tags": tags,
        }

    async def process_articles_async(
        self, session: aiohttp.ClientSession, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        tasks = [self.format_article(session, article) for article in articles]
        return await asyncio.gather(*tasks)

    async def get_articles_async(
        self, page: int = 1, page_size: int = 20
    ) -> List[Dict[str, Any]]:
        if page < 1:
            raise ValueError(
                f"{Fore.RED}Page number cannot be less than 1{Style.RESET_ALL}"
            )

        safe_print(f"{Fore.CYAN}Fetching articles from page {page}{Style.RESET_ALL}")

        offset = (page - 1) * page_size
        params = {
            "id": "archive_story_list",
            "page": "phx-crypto",
            "offset": offset,
            "variation": "archive",
            "type": "lineup_content",
        }

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(self.base_url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()

                articles = data.get("archive_story_list", {}).get("items", [])
                safe_print(
                    f"{Fore.GREEN}✓ Successfully fetched {len(articles)} articles{Style.RESET_ALL}"
                )

                return await self.process_articles_async(session, articles)

        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching articles: {e}{Style.RESET_ALL}")
            return []

    def get_articles(self, page: int = 1, page_size: int = 20) -> List[Dict[str, Any]]:
        async def run():
            async with self as scraper:
                return await scraper.get_articles_async(page, page_size)

        return asyncio.run(run())


async def main_async():
    try:
        async with BloombergScraper(max_concurrent=10) as scraper:
            safe_print(f"{Fore.CYAN}Starting Bloomberg scraper...{Style.RESET_ALL}")
            articles = await scraper.get_articles_async(page=1)
            safe_print(
                f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}"
            )
            print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
