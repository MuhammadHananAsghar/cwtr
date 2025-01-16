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
            'User-Agent': ua.random,
            'Accept': 'application/graphql-response+json, application/graphql+json, application/json, text/event-stream, multipart/mixed',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://cointelegraph.com/',
            'content-type': 'application/json',
            'Origin': 'https://cointelegraph.com',
            'Connection': 'keep-alive',
        }
        self.base_url = 'https://conpletus.cointelegraph.com/v1/'
        self.source_name = "Cointelegraph"
        self.source_url = "https://cointelegraph.com"
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.scraper = cloudscraper.create_scraper()

    def get_graphql_query(self, offset: int = 0, length: int = 100) -> Dict[str, Any]:
        return {
            'operationName': 'MainPagePostsQuery',
            'query': '''query MainPagePostsQuery($short: String, $offset: Int!, $length: Int!, $place: String = 
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
}''',
            'variables': {
                'length': length,
                'offset': offset,
                'short': 'en',
            },
        }

    def get_article_content(self, slug: str) -> str:
        try:
            url = f"https://cointelegraph.com/news/{slug}"
            response = self.scraper.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            content_div = soup.find('div', class_='post__content-wrapper')
            
            if not content_div:
                return ""
                
            paragraphs = []
            for p in content_div.find_all('p'):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
            
            content = ' '.join(paragraphs)
            content = ' '.join(content.split())
            
            safe_print(f"{Fore.GREEN}✓ Successfully fetched content for {slug}{Style.RESET_ALL}")
            return content
            
        except Exception as e:
            safe_print(f"{Fore.RED}✗ Error fetching content for {slug}: {e}{Style.RESET_ALL}")
            return ""

    async def format_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        post_translate = article.get("postTranslate") or {}
        author_translates = (post_translate.get("author") or {}).get("authorTranslates") or [{}]
        category_translates = (article.get("category") or {}).get("categoryTranslates") or [{}]
        
        slug = article.get("slug", "")
        content = self.get_article_content(slug) if slug else ""
        
        return {
            "id": article.get("id", ""),
            "slug": slug,
            "title": post_translate.get("title", ""),
            "content": content,
            "publishedAt": post_translate.get("published", ""),
            "authorName": author_translates[0].get("name"),
            "category": category_translates[0].get("title"),
            "sourceName": self.source_name,
            "sourceUrl": self.source_url
        }

    async def process_articles_async(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [await self.format_article(article) for article in articles]

    async def get_articles_async(self, page: int = 1, page_size: int = 16) -> List[Dict[str, Any]]:
        if page < 1:
            raise ValueError(f"{Fore.RED}Page number cannot be less than 1{Style.RESET_ALL}")

        safe_print(f"{Fore.CYAN}Fetching articles from page {page}{Style.RESET_ALL}")
        
        offset = (page - 1) * page_size
        json_data = self.get_graphql_query(offset=offset, length=page_size)

        try:
            response = self.scraper.post(self.base_url, headers=self.headers, json=json_data)
            response.raise_for_status()
            data = response.json()
            
            articles = data.get("data", {}).get("locale", {}).get("posts", {}).get("data", [])
            safe_print(f"{Fore.GREEN}✓ Successfully fetched {len(articles)} articles{Style.RESET_ALL}")
            return await self.process_articles_async(articles)
            
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