import psycopg2
from psycopg2.extras import execute_values
from openai import OpenAI
from datetime import datetime, timezone
import re
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from colorama import Fore, Style
from psycopg2.extras import DictCursor


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
            batch_size = 20
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

    def get_articles_count(self) -> int:
        """Get total count of articles"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM articles")
            return cur.fetchone()[0]

    def get_articles_filtered(
        self,
        page: int,
        page_size: int,
        source_name: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get filtered articles with pagination"""
        try:
            # Select all columns except embeddings
            query = """
                SELECT 
                    id, slug, title, content, clean_content, 
                    publishedAt, authorName, category, sourceName, 
                    sourceUrl, imageUrl, articleUrl, tags, 
                    createdAt, updatedAt
                FROM articles WHERE 1=1
            """
            params = []
            
            if source_name:
                query += " AND sourceName = %s"
                params.append(source_name)
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM articles WHERE 1=1"
            if source_name:
                count_query += " AND sourceName = %s"
            
            with self.conn.cursor() as cur:
                cur.execute(count_query, [source_name] if source_name else [])
                total = cur.fetchone()[0]
            
            # Get paginated results
            query += " ORDER BY publishedAt DESC NULLS LAST LIMIT %s OFFSET %s"
            params.extend([page_size, (page - 1) * page_size])
            
            with self.conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, params)
                articles = []
                for row in cur.fetchall():
                    article = dict(row)
                    # Convert datetime objects to strings
                    for key in ['publishedAt', 'createdAt', 'updatedAt']:
                        if article.get(key) is not None:
                            article[key] = article[key].isoformat()
                    # Ensure tags is a list
                    if article.get('tags') is None:
                        article['tags'] = []
                    articles.append(article)
            
            return articles, total
        except Exception as e:
            print(f"{Fore.RED}✗ Error getting filtered articles: {e}{Style.RESET_ALL}")
            raise

    def semantic_search(
        self, 
        prompt: str, 
        limit: int = 10,
        published_after: Optional[datetime] = None,
        published_before: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Search articles using cosine similarity with optional date filtering"""
        try:
            # Get embedding for the prompt
            prompt_embedding = self.get_embeddings([prompt])[0]
            
            # Build query with optional date filters
            query = """
                SELECT *, 
                    1 - (embeddings <=> %s::vector) as similarity 
                FROM articles 
                WHERE 1=1
            """
            params = [prompt_embedding]
            
            if published_after:
                query += " AND publishedAt >= %s"
                params.append(published_after)
            if published_before:
                query += " AND publishedAt <= %s"
                params.append(published_before)
            
            # Add ordering and limit
            query += " ORDER BY similarity DESC LIMIT %s"
            params.append(limit)
            
            # Execute search
            with self.conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, params)
                results = cur.fetchall()
                
                # Convert results to dict and format dates
                articles = []
                for row in results:
                    article = dict(row)
                    # Convert datetime objects to strings
                    for key in ['publishedAt', 'createdAt', 'updatedAt']:
                        if article.get(key) is not None:
                            article[key] = article[key].isoformat()
                    articles.append(article)
                
                return articles
            
        except Exception as e:
            print(f"{Fore.RED}✗ Error in semantic search: {e}{Style.RESET_ALL}")
            raise
