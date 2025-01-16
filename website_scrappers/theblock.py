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

class TheBlockScraper:
    def __init__(self, max_concurrent: int = 5):
        ua = UserAgent()
        self.headers = {
            'User-Agent': ua.random,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.theblock.co/latest-crypto-news',
            'Connection': 'keep-alive',
        }
        self.base_url = 'https://www.theblock.co/api/pagesPlus/data/latest-crypto-news'
        self.source_name = "The Block"
        self.source_url = "https://www.theblock.co"
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def clean_html_content(self, html_content: str) -> str:
        if not html_content:
            return ""
            
        soup = BeautifulSoup(html_content, 'html.parser')
        paragraphs = []
        
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if text and not any(disclaimer in text.lower() for disclaimer in ['disclaimer:', '© 2024']):
                paragraphs.append(text)
        
        content = ' '.join(paragraphs)
        content = ' '.join(content.split())
        
        return content

    async def format_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        content = self.clean_html_content(article.get("body", ""))
        
        return {
            "id": str(article.get("id", "")),
            "slug": article.get("slug", ""),
            "title": article.get("title", ""),
            "content": content,
            "publishedAt": article.get("published", ""),
            "authorName": article.get("authors", [{}])[0].get("name") if article.get("authors") else None,
            "category": article.get("primaryCategory", {}).get("name", None),
            "sourceName": self.source_name,
            "sourceUrl": self.source_url
        }

    async def process_articles_async(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [await self.format_article(article) for article in articles]

    async def get_articles_async(self, page: int = 1, page_size: int = 16) -> List[Dict[str, Any]]:
        if page < 1:
            raise ValueError(f"{Fore.RED}Page number cannot be less than 1{Style.RESET_ALL}")

        safe_print(f"{Fore.CYAN}Fetching articles from page {page}{Style.RESET_ALL}")

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(f"{self.base_url}/{page}") as response:
                    response.raise_for_status()
                    data = await response.json()
                
                articles = data.get("latest-crypto-news", {}).get("posts", [])
                safe_print(f"{Fore.GREEN}✓ Successfully fetched {len(articles)} articles{Style.RESET_ALL}")
                
                return await self.process_articles_async(articles)
                
        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching articles: {e}{Style.RESET_ALL}")
            return []

    def get_articles(self, page: int = 1, page_size: int = 16) -> List[Dict[str, Any]]:
        return asyncio.run(self.get_articles_async(page, page_size))

async def main_async():
    try:
        scraper = TheBlockScraper(max_concurrent=10)
        safe_print(f"{Fore.CYAN}Starting The Block scraper...{Style.RESET_ALL}")
        articles = await scraper.get_articles_async(page=1)
        safe_print(f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}")
        print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main() 