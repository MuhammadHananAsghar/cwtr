import json
import asyncio
import aiohttp
from typing import List, Dict, Any
from datetime import datetime
from colorama import Fore, Style, init
from threading import Lock
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import cloudscraper

init(autoreset=True)

print_lock = Lock()


def safe_print(message: str):
    with print_lock:
        print(message)


class CointelegraphScraper:
    def __init__(self, max_concurrent: int = 5):
        ua = UserAgent()
        self.headers = {
            "User-Agent": ua.random,
            "Accept": "application/graphql-response+json, application/graphql+json, application/json, text/event-stream, multipart/mixed",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://cointelegraph.com/",
            "content-type": "application/json",
            "Origin": "https://cointelegraph.com",
            "Connection": "keep-alive",
        }
        self.base_url = "https://conpletus.cointelegraph.com/v1/"
        self.source_name = "Cointelegraph"
        self.source_url = "https://cointelegraph.com"
        self.article_base_url = "https://cointelegraph.com/news"
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.scraper = cloudscraper.create_scraper()

    def get_graphql_query(self, offset: int = 0, length: int = 100) -> Dict[str, Any]:
        return {
            "operationName": "MainPagePostsQuery",
            "query": """query MainPagePostsQuery($short: String, $offset: Int!, $length: Int!, $place: String = 
"index", $beforePublishedAt: DateTime = null) {
  locale(short: $short) {
    posts(
      order: "postPublishedTime"
      offset: $offset
      length: $length
      place: $place
      beforePublishedAt: $beforePublishedAt
    ) {
      data {
        id
        slug
        postTranslate {
          id
          title
          published
          leadText
          author {
            authorTranslates {
              name
              __typename
            }
            __typename
          }
          __typename
        }
        postBadge {
          postBadgeTranslates {
            title
            __typename
          }
          __typename
        }
        category {
          categoryTranslates {
            title
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}""",
            "variables": {
                "length": length,
                "offset": offset,
                "short": "en",
            },
        }

    def get_article_content(self, slug: str) -> str:
        try:
            safe_print(f"{Fore.YELLOW}⟳ Fetching content for: {slug}{Style.RESET_ALL}")

            if slug.startswith("http"):
                slug = (
                    slug.split("/news/")[-1]
                    if "/news/" in slug
                    else slug.split("/")[-1]
                )
                article_url = f"{self.article_base_url}/{slug}"
            else:
                article_url = f"{self.article_base_url}/{slug}"
            article_url = article_url.replace("//", "/").replace("https:/", "https://")

            response = self.scraper.get(article_url, headers=self.headers)
            if response.status_code != 200:
                safe_print(
                    f"{Fore.RED}✗ Failed to fetch content for: {slug}{Style.RESET_ALL}"
                )
                return ""

            soup = BeautifulSoup(response.content, "html.parser")
            content_div = soup.find("div", class_="post__content-wrapper")

            if not content_div:
                safe_print(f"{Fore.RED}✗ No content found for: {slug}{Style.RESET_ALL}")
                return ""

            paragraphs = []
            for p in content_div.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)

            content = " ".join(paragraphs)
            content = " ".join(content.split())

            safe_print(
                f"{Fore.GREEN}✓ Successfully fetched content for: {slug}{Style.RESET_ALL}"
            )
            return content

        except Exception as e:
            safe_print(
                f"{Fore.RED}✗ Error fetching content for {slug}: {e}{Style.RESET_ALL}"
            )
            return ""

    async def format_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        try:
            post_translate = article.get("postTranslate") or {}
            author_translates = (post_translate.get("author") or {}).get(
                "authorTranslates"
            ) or [{}]

            post_badge = article.get("postBadge", {})
            badge_translates = post_badge.get("postBadgeTranslates", [])
            tags = []
            if badge_translates:
                tags = [
                    badge.get("title")
                    for badge in badge_translates
                    if badge and badge.get("title")
                ]

            category_translates = (article.get("category") or {}).get(
                "categoryTranslates"
            ) or [{}]

            slug = article.get("slug", "")
            title = post_translate.get("title", "")
            safe_print(f"{Fore.YELLOW}⟳ Processing article: {title}{Style.RESET_ALL}")

            content = self.get_article_content(slug) if slug else ""

            formatted_article = {
                "id": article.get("id", ""),
                "slug": slug,
                "title": title,
                "content": content,
                "publishedAt": post_translate.get("published", ""),
                "authorName": author_translates[0].get("name"),
                "category": category_translates[0].get("title"),
                "sourceName": self.source_name,
                "sourceUrl": self.source_url,
                "imageUrl": post_translate.get("avatar"),
                "articleUrl": f"{self.source_url}/news/{slug}",
                "tags": tags,
            }

            safe_print(
                f"{Fore.GREEN}✓ Successfully processed: {title}{Style.RESET_ALL}"
            )
            return formatted_article

        except Exception as e:
            safe_print(
                f"{Fore.RED}✗ Error processing article {post_translate.get('title', 'Unknown')}: {e}{Style.RESET_ALL}"
            )
            return None

    async def process_articles_async(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        return [await self.format_article(article) for article in articles]

    async def get_articles_async(
        self, page: int = 1, page_size: int = 16
    ) -> List[Dict[str, Any]]:
        if page < 1:
            raise ValueError(
                f"{Fore.RED}Page number cannot be less than 1{Style.RESET_ALL}"
            )

        safe_print(
            f"{Fore.YELLOW}⟳ Fetching Cointelegraph articles list...{Style.RESET_ALL}"
        )

        offset = (page - 1) * page_size
        json_data = self.get_graphql_query(offset=offset, length=page_size)

        try:
            response = self.scraper.post(
                self.base_url, headers=self.headers, json=json_data
            )
            if response.status_code != 200:
                safe_print(
                    f"{Fore.RED}✗ Failed to fetch articles: {response.status_code}{Style.RESET_ALL}"
                )
                return []

            data = response.json()
            articles = (
                data.get("data", {}).get("locale", {}).get("posts", {}).get("data", [])
            )
            safe_print(f"{Fore.GREEN}✓ Found {len(articles)} articles{Style.RESET_ALL}")

            processed_articles = await self.process_articles_async(articles)
            safe_print(
                f"{Fore.GREEN}✓ Successfully processed {len(processed_articles)} articles{Style.RESET_ALL}"
            )
            return processed_articles

        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching articles: {e}{Style.RESET_ALL}")
            return []

    def get_articles(self, page: int = 1, page_size: int = 16) -> List[Dict[str, Any]]:
        return asyncio.run(self.get_articles_async(page, page_size))


async def main_async():
    try:
        scraper = CointelegraphScraper(max_concurrent=10)
        safe_print(f"{Fore.CYAN}Starting Cointelegraph scraper...{Style.RESET_ALL}")
        articles = await scraper.get_articles_async(page=1)
        safe_print(f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}")
        print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
