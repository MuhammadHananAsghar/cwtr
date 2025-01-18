import json
import asyncio
import aiohttp
from typing import List, Dict, Any
from datetime import datetime, timezone
from colorama import Fore, Style, init
from threading import Lock
from bs4 import BeautifulSoup
import cloudscraper
from fake_useragent import UserAgent
from datetime import datetime, timezone, timedelta

init(autoreset=True)

print_lock = Lock()


def safe_print(message: str):
    with print_lock:
        print(message)


class CryptoNewsScraper:
    def __init__(self, max_concurrent: int = 5):
        ua = UserAgent()
        self.headers = {
            "User-Agent": ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }
        self.base_url = "https://cryptonews.com"
        self.source_name = "Cryptonews"
        self.source_url = "https://cryptonews.com"
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.scraper = cloudscraper.create_scraper()

    def extract_articles_from_html(self, html_content: str) -> List[Dict[str, Any]]:
        """Extract article information from HTML content"""
        soup = BeautifulSoup(html_content, "html.parser")
        articles = []

        article_elements = soup.find_all("div", class_="top-story-cell-top__wrap")

        for article in article_elements:
            try:
                link_element = article.find("a", class_="top-story-cell")
                if not link_element:
                    continue

                article_url = link_element.get("href", "")
                if not article_url.startswith("http"):
                    article_url = f"{self.base_url}{article_url}"

                # Extract slug from article URL
                slug = (
                    article_url.split("/news/")[-1].rstrip("/")
                    if "/news/" in article_url
                    else ""
                )

                # Extract title
                title_element = link_element.find("div", class_="top-story-cell__title")
                title = title_element.get_text(strip=True) if title_element else ""

                # Extract category
                category_element = link_element.find(
                    "div", class_="top-story-cell__term"
                )
                category = (
                    category_element.get_text(strip=True)
                    if category_element
                    else "Crypto"
                )

                # Extract author
                author_element = link_element.find(
                    "div", class_="top-story-cell__author"
                )
                author = (
                    author_element.get_text(strip=True).replace("by ", "")
                    if author_element
                    else "Cryptonews"
                )

                # Extract image URL
                image_div = link_element.find("div", class_="top-story-cell-top__bg")
                image_url = (
                    image_div.get("style", "").split("url(")[-1].split(")")[0]
                    if image_div
                    else ""
                )
                # Clean up the URL
                image_url = image_url.strip("'").strip('"') if image_url else ""

                # Extract date
                date_element = link_element.find("div", class_="top-story-cell__time")
                if date_element and date_element.get("data-utctime"):
                    published_at = datetime.strptime(
                        date_element["data-utctime"], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                else:
                    published_at = datetime.now(timezone.utc)

                article_data = {
                    "id": slug,
                    "slug": slug,
                    "title": title,
                    "content": "",
                    "publishedAt": published_at.isoformat(),
                    "authorName": author,
                    "category": category,
                    "sourceName": self.source_name,
                    "sourceUrl": self.source_url,
                    "articleUrl": article_url,
                    "imageUrl": image_url,
                    "tags": [],  # Will be populated when fetching content
                }
                articles.append(article_data)

            except Exception as e:
                safe_print(
                    f"{Fore.RED}✗ Error processing article: {e}{Style.RESET_ALL}"
                )
                continue

        return articles

    async def get_articles_async(
        self, page: int = 1, page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """Fetch articles asynchronously"""
        try:
            response = self.scraper.get(self.base_url, headers=self.headers)
            response.raise_for_status()

            articles = self.extract_articles_from_html(response.text)

            # Limit articles based on page_size
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            articles = articles[start_idx:end_idx]

            # Process articles and fetch content concurrently
            processed_articles = await self.process_articles_async(articles)

            safe_print(
                f"{Fore.GREEN}✓ Successfully fetched {len(processed_articles)} articles with content{Style.RESET_ALL}"
            )
            return processed_articles

        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching articles: {e}{Style.RESET_ALL}")
            return []

    def get_articles(self, page: int = 1, page_size: int = 20) -> List[Dict[str, Any]]:
        return asyncio.run(self.get_articles_async(page, page_size))

    async def get_article_content(
        self, session: aiohttp.ClientSession, url: str, title: str
    ) -> tuple[str, list]:
        """Fetch article content asynchronously"""
        try:
            async with self.semaphore:
                safe_print(
                    f"{Fore.YELLOW}⟳ Fetching content for: {title}{Style.RESET_ALL}"
                )

                response = self.scraper.get(url, headers=self.headers)
                if response.status_code != 200:
                    safe_print(
                        f"{Fore.RED}✗ Failed to fetch content for: {title}{Style.RESET_ALL}"
                    )
                    return "", []

                soup = BeautifulSoup(response.text, "html.parser")

                # Extract tags
                tags = []
                tags_div = soup.find("div", class_="single-post-new__tags")
                if tags_div:
                    tag_spans = tags_div.find_all("span", class_="value")
                    tags = [span.get_text(strip=True) for span in tag_spans]

                # Extract content
                content_div = soup.find("div", class_="article-single__content")
                if not content_div:
                    safe_print(
                        f"{Fore.RED}✗ No content found for: {title}{Style.RESET_ALL}"
                    )
                    return "", tags

                paragraphs = []
                for p in content_div.find_all(["p", "h2"]):
                    if any(
                        cls in str(p.parent.get("class", []))
                        for cls in [
                            "interlinking-shortcode",
                            "follow-button",
                            "news-tab",
                        ]
                    ):
                        continue

                    if p.get("class") and any(
                        cls in p.get("class") for cls in ["replacer"]
                    ):
                        continue

                    text = p.get_text(strip=True)
                    if text:
                        paragraphs.append(text)

                content = " ".join(paragraphs)
                safe_print(
                    f"{Fore.GREEN}✓ Successfully fetched content for: {title}{Style.RESET_ALL}"
                )
                return content, tags

        except Exception as e:
            safe_print(
                f"{Fore.RED}✗ Error fetching content for {title}: {e}{Style.RESET_ALL}"
            )
            return "", []

    async def process_articles_async(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process articles concurrently"""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = []
            for article in articles:
                article_url = article.get("articleUrl", "")
                title = article.get("title", "")
                if article_url:
                    content = asyncio.create_task(
                        self.get_article_content(session, article_url, title)
                    )
                    tasks.append((article, content))

            processed_articles = []
            for article, content_task in tasks:
                try:
                    content, tags = await content_task
                    article["content"] = content
                    article["tags"] = tags
                    processed_articles.append(article)
                except Exception as e:
                    safe_print(
                        f"{Fore.RED}✗ Error processing article: {e}{Style.RESET_ALL}"
                    )
                    article["content"] = ""
                    article["tags"] = []
                    processed_articles.append(article)

            return processed_articles


async def main_async():
    try:
        scraper = CryptoNewsScraper(max_concurrent=10)
        safe_print(f"{Fore.CYAN}Starting Cryptonews scraper...{Style.RESET_ALL}")
        articles = await scraper.get_articles_async(page=1)
        safe_print(f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}")
        print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
