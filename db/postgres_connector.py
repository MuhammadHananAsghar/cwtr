import psycopg2
from psycopg2.extras import execute_values
from openai import OpenAI
from datetime import datetime, timezone
import re
from typing import List, Dict, Any
import numpy as np
from colorama import Fore, Style


class PostgresConnector:
    def __init__(self, config: Dict[str, Any], openai_api_key: str):
        self.config = config
        self.conn = None
        self.connect()
        self.create_table()
        self.client = OpenAI(api_key=openai_api_key)

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.config["host"],
                port=self.config["port"],
                user=self.config["user"],
                password=self.config["password"],
                database=self.config["database"],
            )
            print(
                f"{Fore.GREEN}✓ Successfully connected to PostgreSQL{Style.RESET_ALL}"
            )
        except Exception as e:
            print(f"{Fore.RED}✗ Error connecting to PostgreSQL: {e}{Style.RESET_ALL}")
            raise

    def create_table(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS articles (
                        id VARCHAR(255),
                        slug VARCHAR(255),
                        title TEXT,
                        content TEXT,
                        clean_content TEXT,
                        publishedAt TIMESTAMP WITH TIME ZONE,
                        authorName VARCHAR(255),
                        category VARCHAR(255),
                        sourceName VARCHAR(255),
                        sourceUrl VARCHAR(255),
                        imageUrl TEXT,
                        articleUrl TEXT,
                        tags TEXT[],
                        embeddings VECTOR(1536),
                        createdAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT articles_unique_id UNIQUE (id),
                        CONSTRAINT articles_unique_slug_source UNIQUE (slug, sourceName),
                        CONSTRAINT articles_unique_title_source UNIQUE (title, sourceName),
                        CONSTRAINT articles_pk PRIMARY KEY (id)
                    )
                """
                )
                self.conn.commit()
                print(f"{Fore.GREEN}✓ Table 'articles' ready{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error creating table: {e}{Style.RESET_ALL}")
            raise

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        try:
            response = self.client.embeddings.create(
                model="text-embedding-ada-002", input=texts
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            print(f"{Fore.RED}✗ Error getting embeddings: {e}{Style.RESET_ALL}")
            raise

    def check_duplicates(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Check for duplicates and return only new articles"""
        try:
            new_articles = []
            with self.conn.cursor() as cur:
                for article in articles:
                    cur.execute(
                        """
                        SELECT id FROM articles 
                        WHERE id = %s 
                        OR (slug = %s AND sourceName = %s)
                        OR (title = %s AND sourceName = %s)
                    """,
                        (
                            article["id"],
                            article["slug"],
                            article["sourceName"],
                            article["title"],
                            article["sourceName"],
                        ),
                    )
                    if not cur.fetchone():
                        new_articles.append(article)

            print(
                f"{Fore.GREEN}✓ Found {len(new_articles)} new articles out of {len(articles)}{Style.RESET_ALL}"
            )
            return new_articles
        except Exception as e:
            print(f"{Fore.RED}✗ Error checking duplicates: {e}{Style.RESET_ALL}")
            raise

    def save_articles(self, articles: List[Dict[str, Any]]):
        try:
            # Check for duplicates first
            new_articles = self.check_duplicates(articles)
            if not new_articles:
                print(f"{Fore.YELLOW}⚠ No new articles to save{Style.RESET_ALL}")
                return

            # Get embeddings only for new articles
            batch_size = 30
            all_embeddings = []
            for i in range(0, len(new_articles), batch_size):
                batch = new_articles[i : i + batch_size]
                texts = [article["clean_content"] for article in batch]
                embeddings = self.get_embeddings(texts)
                all_embeddings.extend(embeddings)

            values = []
            for article, embedding in zip(new_articles, all_embeddings):
                values.append(
                    (
                        article["id"],
                        article["slug"],
                        article["title"],
                        article["content"],
                        article["clean_content"],
                        article["publishedAt"],
                        article["authorName"],
                        article["category"],
                        article["sourceName"],
                        article["sourceUrl"],
                        article["imageUrl"],
                        article["articleUrl"],
                        article.get("tags", []),
                        embedding,
                        datetime.now(timezone.utc),
                    )
                )

            with self.conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO articles (
                        id, slug, title, content, clean_content, publishedAt,
                        authorName, category, sourceName, sourceUrl, imageUrl,
                        articleUrl, tags, embeddings, createdAt
                    ) VALUES %s
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        clean_content = EXCLUDED.clean_content,
                        embeddings = EXCLUDED.embeddings,
                        updatedAt = CURRENT_TIMESTAMP
                    WHERE articles.id = EXCLUDED.id
                    OR (articles.slug = EXCLUDED.slug AND articles.sourceName = EXCLUDED.sourceName)
                    OR (articles.title = EXCLUDED.title AND articles.sourceName = EXCLUDED.sourceName)
                    """,
                    values,
                )
                self.conn.commit()
                print(
                    f"{Fore.GREEN}✓ Successfully saved {len(new_articles)} new articles{Style.RESET_ALL}"
                )
        except Exception as e:
            print(f"{Fore.RED}✗ Error saving articles: {e}{Style.RESET_ALL}")
            self.conn.rollback()
            raise

    def close(self):
        if self.conn:
            self.conn.close()
