import json
import asyncio
import aiohttp
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


class CoindeskScraper:
    def __init__(self, max_concurrent: int = 5):
        ua = UserAgent()
        self.headers = {
            "User-Agent": ua.random,
            "Accept": "text/x-component",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.coindesk.com/",
            "Next-Action": "40e2c881baef274abca4f12f54acf2d96cb0f3fbf7",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.coindesk.com",
            "Connection": "keep-alive",
        }
        self.base_url = "https://www.coindesk.com/"
        self.source_name = "Coindesk"
        self.source_url = "https://www.coindesk.com"
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def extract_text_from_html(self, html_content: str) -> str:
        if not html_content:
            return ""

        soup = BeautifulSoup(html_content, "html.parser")
        paragraphs = []

        article = soup.find("article") or soup

        for p in article.find_all("p"):
            text = p.get_text(strip=True)
            if text and not any(
                footer in text.upper() for footer in ["ABOUT", "CONTACT", "POLICIES"]
            ):
                paragraphs.append(text)

        content = " ".join(paragraphs)
        content = " ".join(content.split())

        return content

    async def get_article_content(
        self, session: aiohttp.ClientSession, pathname: str
    ) -> str:
        try:
            async with self.semaphore:
                url = f"{self.base_url.rstrip('/')}{pathname}"
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    html_content = await response.text()
                    content = self.extract_text_from_html(html_content)

                    if content:
                        safe_print(
                            f"{Fore.GREEN}✓ Successfully fetched content for article {pathname}{Style.RESET_ALL}"
                        )
                        return content
                    else:
                        safe_print(
                            f"{Fore.YELLOW}⚠ No content found for article {pathname}{Style.RESET_ALL}"
                        )
                        return ""

        except Exception as e:
            safe_print(
                f"{Fore.RED}✗ Error fetching article content for {pathname}: {e}{Style.RESET_ALL}"
            )
            return ""

    def extract_articles_from_response(
        self, response_text: str
    ) -> List[Dict[str, Any]]:
        try:
            start_index = response_text.find('"articles":[')
            if start_index == -1:
                return []

            bracket_count = 0
            end_index = start_index
            while end_index < len(response_text):
                if response_text[end_index] == "[":
                    bracket_count += 1
                elif response_text[end_index] == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        break
                end_index += 1

            articles_json_str = response_text[
                start_index + len('"articles":') : end_index + 1
            ]
            return json.loads(articles_json_str)
        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error parsing articles JSON: {e}{Style.RESET_ALL}")
            return []

    async def format_article(
        self, session: aiohttp.ClientSession, article: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format article data into standardized structure"""
        pathname = article.get("pathname", "")
        content = await self.get_article_content(session, pathname) if pathname else ""

        # Extract tags from tagDetails
        tags = []
        tag_details = article.get("tagDetails", [])
        if tag_details:
            tags = [tag.get("title") for tag in tag_details if tag and tag.get("title")]

        # Extract image URL from featuredImages
        image_url = ""
        featured_images = article.get("__featuredImages", [])
        if featured_images:
            first_image = featured_images[0].get("source", {})
            image_url = first_image.get("src", "")

        return {
            "id": article.get("_id", ""),
            "slug": pathname.split("/")[-1],
            "title": article.get("title", ""),
            "content": content,
            "publishedAt": article.get("articleDates", {}).get("publishedAt", ""),
            "authorName": article.get("authorDetails", [{}])[0].get("byline", None),
            "category": article.get("sectionDetails", [{}])[0].get("name", None),
            "sourceName": self.source_name,
            "sourceUrl": self.source_url,
            "imageUrl": image_url,
            "articleUrl": f"{self.source_url}{pathname}",
            "tags": tags,
        }

    async def process_articles_async(
        self, session: aiohttp.ClientSession, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process articles concurrently"""
        tasks = [self.format_article(session, article) for article in articles]
        return await asyncio.gather(*tasks)

    async def get_articles_async(
        self, page: int = 1, page_size: int = 16
    ) -> List[Dict[str, Any]]:
        if page < 1:
            raise ValueError(
                f"{Fore.RED}Page number cannot be less than 1{Style.RESET_ALL}"
            )

        safe_print(f"{Fore.CYAN}Fetching articles from page {page}{Style.RESET_ALL}")

        data = json.dumps([{"size": page_size, "page": page}])

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(self.base_url, data=data) as response:
                    response.raise_for_status()
                    response_text = await response.text()

                articles = self.extract_articles_from_response(response_text)
                safe_print(
                    f"{Fore.GREEN}✓ Successfully fetched {len(articles)} articles{Style.RESET_ALL}"
                )

                return await self.process_articles_async(session, articles)

        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching articles: {e}{Style.RESET_ALL}")
            return []

    def get_articles(self, page: int = 1, page_size: int = 16) -> List[Dict[str, Any]]:
        return asyncio.run(self.get_articles_async(page, page_size))


async def main_async():
    try:
        scraper = CoindeskScraper(max_concurrent=10)
        safe_print(f"{Fore.CYAN}Starting Coindesk scraper...{Style.RESET_ALL}")
        articles = await scraper.get_articles_async(page=1)
        safe_print(f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}")
        print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
