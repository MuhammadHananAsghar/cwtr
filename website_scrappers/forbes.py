import json
import asyncio
import aiohttp
from typing import List, Dict, Any
from datetime import datetime
from colorama import Fore, Style, init
from threading import Lock
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
from urllib.parse import urlparse

init(autoreset=True)

print_lock = Lock()
def safe_print(message: str):
    with print_lock:
        print(message)

class ForbesScraper:
    def __init__(self, max_concurrent: int = 5):
        ua = UserAgent()
        self.headers = {
            'User-Agent': ua.random,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.forbes.com/digital-assets/news/',
        }
        self.base_url = 'https://www.forbes.com/digital-assets/_next/data/0lOZ_TN7MA2GUEm9YUHLu/news.json'
        self.source_name = "Forbes"
        self.source_url = "https://www.forbes.com/digital-assets/"
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        self.scraper = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.scraper.close()

    def extract_slug(self, url: str) -> str:
        """Extract slug from Forbes URL."""
        path = urlparse(url).path
        return path.split('/')[-1] if path else ""

    async def get_article_content(self, url: str) -> str:
        """Fetch and extract article content from Forbes article page."""
        try:
            async with self.scraper.get(url) as response:
                if response.status != 200:
                    return ""
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find the article body div
                article_body = soup.find('div', {'class': 'article-body'})
                if not article_body:
                    return ""
                
                # Get all paragraphs from article body
                paragraphs = article_body.find_all('p')
                content = ' '.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
                
                return content

        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching article content: {e}{Style.RESET_ALL}")
            return ""

    async def get_articles_async(self, page: int = 1, page_size: int = 20) -> List[Dict[str, Any]]:
        try:
            async with self.scraper.get(self.base_url) as response:
                if response.status != 200:
                    safe_print(f"{Fore.RED}✗ Error fetching articles: {response.status}{Style.RESET_ALL}")
                    return []

                data = await response.json()
                articles = data.get("pageProps", {}).get("initialData", {}).get("latestNewsServerData", {}).get("latest", [])
                
                processed_articles = []
                for article in articles[:page_size]:
                    url = article.get("uri", "")
                    content = await self.get_article_content(url)
                    
                    processed_article = {
                        "id": article.get("id", ""),
                        "slug": self.extract_slug(url),
                        "title": article.get("title", ""),
                        "content": content,
                        "publishedAt": article.get("date", ""),
                        "authorName": article.get("author", {}).get("name", ""),
                        "category": "Crypto",
                        "sourceName": self.source_name,
                        "sourceUrl": self.source_url
                    }
                    processed_articles.append(processed_article)
                    safe_print(f"{Fore.GREEN}✓ Fetched content for: {processed_article['title']}{Style.RESET_ALL}")

                return processed_articles

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
        async with ForbesScraper(max_concurrent=10) as scraper:
            safe_print(f"{Fore.CYAN}Starting Forbes scraper...{Style.RESET_ALL}")
            articles = await scraper.get_articles_async(page=1)
            safe_print(f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}")
            print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main() 