import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from colorama import Fore, Style, init
import schedule
import time
import re
from website_scrappers.bloomberg import BloombergScraper
from website_scrappers.coindesk import CoindeskScraper
from website_scrappers.cointelegraph import CointelegraphScraper
from website_scrappers.decrypt import DecryptScraper
from website_scrappers.forbes import ForbesScraper
from website_scrappers.theblock import TheBlockScraper
from website_scrappers.cryptonews import CryptoNewsScraper
import config
from db.postgres_connector import PostgresConnector

init(autoreset=True)


def clean_content(text: str) -> str:
    text = re.sub(r"http\S+|www.\S+", "", text)
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    text = " ".join(text.split())
    text = text.lower()
    return text


def filter_articles_by_time(
    articles: List[Dict[str, Any]], past_minutes: int
) -> List[Dict[str, Any]]:
    current_time = datetime.now(timezone.utc)
    cutoff_time = current_time - timedelta(minutes=past_minutes)

    filtered_articles = []
    for article in articles:
        article["clean_content"] = clean_content(article["content"])
        filtered_articles.append(article)
        # try:
        #     published_at = datetime.fromisoformat(
        #         article["publishedAt"].replace("Z", "+00:00")
        #     )
        #     if not published_at.tzinfo:
        #         published_at = published_at.replace(tzinfo=timezone.utc)

        #     if published_at >= cutoff_time:
        #         filtered_articles.append(article)
        # except (ValueError, KeyError) as e:
        #     print(
        #         f"{Fore.YELLOW}⚠ Warning: Could not parse date for article: {article.get('title', 'Unknown')}{Style.RESET_ALL}"
        #     )
        #     continue

    return filtered_articles


async def run_scraper(scraper_class, name: str) -> List[Dict[str, Any]]:
    try:
        if hasattr(scraper_class, "__aenter__"):
            async with scraper_class(
                max_concurrent=config.SCRAPER_CONFIG["max_concurrent"]
            ) as scraper:
                articles = await scraper.get_articles_async(
                    page=1, page_size=config.SCRAPER_CONFIG["page_size"]
                )
        else:
            scraper = scraper_class(
                max_concurrent=config.SCRAPER_CONFIG["max_concurrent"]
            )
            articles = await scraper.get_articles_async(
                page=1, page_size=config.SCRAPER_CONFIG["page_size"]
            )

        print(
            f"{Fore.GREEN}✓ Successfully fetched {len(articles)} articles from {name}{Style.RESET_ALL}"
        )
        return articles
    except Exception as e:
        print(f"{Fore.RED}✗ Error running {name} scraper: {e}{Style.RESET_ALL}")
        return []


async def run_all_scrapers() -> List[Dict[str, Any]]:
    scrapers = [
        (BloombergScraper, "Bloomberg"),
        (CoindeskScraper, "Coindesk"),
        (CointelegraphScraper, "Cointelegraph"),
        (DecryptScraper, "Decrypt"),
        (ForbesScraper, "Forbes"),
        (TheBlockScraper, "The Block"),
        (CryptoNewsScraper, "Crypto News"),
    ]

    print(f"{Fore.CYAN}Starting all scrapers...{Style.RESET_ALL}")
    tasks = [run_scraper(scraper_class, name) for scraper_class, name in scrapers]
    results = await asyncio.gather(*tasks)
    all_articles = []
    for articles in results:
        all_articles.extend(articles)
    filtered_articles = filter_articles_by_time(
        all_articles, config.SCRAPER_CONFIG["past_period"]
    )
    filtered_articles.sort(key=lambda x: x["publishedAt"], reverse=True)

    print(
        f"{Fore.GREEN}✓ Total articles after filtering: {len(filtered_articles)}{Style.RESET_ALL}"
    )
    return filtered_articles


def run_scraper_job():
    """Job to be run on schedule"""
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{Fore.CYAN}Starting scheduled run at {current_time}{Style.RESET_ALL}")

        articles = asyncio.run(run_all_scrapers())
        db = PostgresConnector(config.POSTGRES_CONFIG, config.OPENAI_API_KEY)
        try:
            db.save_articles(articles)
        finally:
            db.close()

        print(
            f"\n{Fore.CYAN}Total articles saved to database: {len(articles)} for last {config.SCRAPER_CONFIG['past_period']} minutes.{Style.RESET_ALL}"
        )
        print(
            f"{Fore.CYAN}Next run in {config.SCRAPER_CONFIG['run_interval']} minutes{Style.RESET_ALL} at {datetime.now() + timedelta(minutes=config.SCRAPER_CONFIG['run_interval'])}{Style.RESET_ALL}"
        )

    except Exception as e:
        print(f"{Fore.RED}✗ Fatal error: {e}{Style.RESET_ALL}")


def main():
    """Main entry point"""
    print(f"{Fore.CYAN}Starting crypto news scraper service...{Style.RESET_ALL}")
    print(
        f"{Fore.CYAN}Will run every {config.SCRAPER_CONFIG['run_interval']} minutes{Style.RESET_ALL}"
    )

    # Run immediately on startup
    run_scraper_job()

    # Schedule regular runs
    schedule.every(config.SCRAPER_CONFIG["run_interval"]).minutes.do(run_scraper_job)

    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
