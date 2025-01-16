import json
import asyncio
import aiohttp
from typing import List, Dict, Any
from datetime import datetime
from colorama import Fore, Style, init
from threading import Lock
from bs4 import BeautifulSoup
import re
from fake_useragent import UserAgent

init(autoreset=True)

print_lock = Lock()
def safe_print(message: str):
    with print_lock:
        print(message)

class DecryptScraper:
    def __init__(self, max_concurrent: int = 5):
        ua = UserAgent()
        self.headers = {
            'User-Agent': ua.random,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://decrypt.co/',
            'Apollo-Require-Preflight': 'true',
            'Origin': 'https://decrypt.co',
            'Connection': 'keep-alive',
        }
        self.base_url = 'https://gateway.decrypt.co/'
        self.article_base_url = 'https://decrypt.co/_next/data/1DAsWX9DvodIzQ0WRMepi/en-US'
        self.source_name = "Decrypt"
        self.source_url = "https://decrypt.co"
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def clean_html_content(self, html_content: str) -> str:
        if not html_content:
            return ""
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for embedded in soup.find_all(class_='embedded-post'):
            embedded.decompose()
            
        paragraphs = []
        for p in soup.find_all('p'):
            text_parts = []
            for element in p.stripped_strings:
                text_parts.append(element)
            
            if text_parts:
                paragraphs.append(' '.join(text_parts))
        
        content = ' '.join(paragraphs)
        content = ' '.join(content.split())
        
        return content

    async def get_full_article_content(self, session: aiohttp.ClientSession, article_id: str, slug: str) -> str:
        try:
            async with self.semaphore:
                params = {
                    'post_id': article_id,
                    'slug': slug,
                }
                
                url = f"{self.article_base_url}/{article_id}/{slug}.json"
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    article_data = await response.json()
                
                html_content = article_data.get("pageProps", {}).get("activeArticle", {}).get("activeArticle", {}).get("content", "")
                clean_content = self.clean_html_content(html_content)
                
                if clean_content:
                    safe_print(f"{Fore.GREEN}✓ Successfully fetched content for article {article_id}{Style.RESET_ALL}")
                    return clean_content
                else:
                    safe_print(f"{Fore.YELLOW}⚠ No content found for article {article_id}{Style.RESET_ALL}")
                    return ""
                    
        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching article content for {article_id}: {e}{Style.RESET_ALL}")
            return ""

    async def format_article_with_content(self, session: aiohttp.ClientSession, article: Dict[str, Any]) -> Dict[str, Any]:
        article_id = str(article.get("id", ""))
        slug = article.get("slug", "")
        content = await self.get_full_article_content(session, article_id, slug)
        
        return {
            "id": article_id,
            "slug": slug,
            "title": article.get("title"),
            "content": content,
            "publishedAt": article.get("publishedAt"),
            "authorName": article["authors"]["data"][0]["name"] if article.get("authors", {}).get("data") else None,
            "category": article["category"]["data"]["name"] if article.get("category", {}).get("data") else None,
            "sourceName": self.source_name,
            "sourceUrl": self.source_url
        }

    async def process_articles_async(self, session: aiohttp.ClientSession, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tasks = [
            self.format_article_with_content(session, article)
            for article in articles
        ]
        return await asyncio.gather(*tasks)

    async def get_articles_async(self, page: int = 0, page_size: int = 12) -> List[Dict[str, Any]]:
        if page < 0:
            raise ValueError(f"{Fore.RED}Page number cannot be negative{Style.RESET_ALL}")

        safe_print(f"{Fore.CYAN}Fetching articles from page {page}{Style.RESET_ALL}")

        params = {
            'variables': json.dumps({
                "filters": {
                    "locale": {"eq": "en"},
                    "category": {"slug": {"eq": "news"}}
                },
                "pagination": {
                    "pageSize": page_size,
                    "page": page
                },
                "sort": ["publishedAt:desc"]
            }),
            'operationName': 'ArticlePreviews',
            'extensions': json.dumps({
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "7366f3114618c1df3a4b718a7b3e6f93cb804c036a907f52a75b108d9645618f"
                }
            })
        }

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(self.base_url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                
                articles = data.get("data", {}).get("articles", {}).get("data", [])
                safe_print(f"{Fore.GREEN}✓ Successfully fetched {len(articles)} articles{Style.RESET_ALL}")
                
                return await self.process_articles_async(session, articles)
                
        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching articles: {e}{Style.RESET_ALL}")
            return []

    def get_articles(self, page: int = 0, page_size: int = 12) -> List[Dict[str, Any]]:
        return asyncio.run(self.get_articles_async(page, page_size))

async def main_async():
    try:
        scraper = DecryptScraper(max_concurrent=10)
        safe_print(f"{Fore.CYAN}Starting Decrypt scraper...{Style.RESET_ALL}")
        articles = await scraper.get_articles_async(page=1)
        safe_print(f"{Fore.GREEN}✓ Scraping completed successfully{Style.RESET_ALL}")
        print(json.dumps(articles, indent=2))
    except Exception as e:
        safe_print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()