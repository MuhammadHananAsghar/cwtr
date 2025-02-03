from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel, Field
from psycopg2.extras import DictCursor
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain.chains import create_sql_query_chain
import config
from db.postgres_connector import PostgresConnector


OPENAI_API_KEY = config.OPENAI_API_KEY
client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="Crypto News API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ArticleResponse(BaseModel):
    id: str
    slug: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    clean_content: Optional[str] = None
    publishedAt: Optional[str] = None
    authorName: Optional[str] = None
    category: Optional[str] = None
    sourceName: Optional[str] = None
    sourceUrl: Optional[str] = None
    imageUrl: Optional[str] = None
    articleUrl: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    class Config:
        from_attributes = True

class ArticlesPage(BaseModel):
    total: int
    page: int
    page_size: int
    articles: List[ArticleResponse]

    class Config:
        from_attributes = True

class SearchRequest(BaseModel):
    prompt: str
    system_prompt: str = Field(default="You are a helpful assistant that provides insights based on crypto news articles.")
    model: str = Field(default="gpt-4o-mini")

@app.get("/articles/count")
async def get_articles_count():
    """Get total count of articles in database"""
    try:
        db = PostgresConnector(config.POSTGRES_CONFIG, OPENAI_API_KEY)
        count = db.get_articles_count()
        return {"total_articles": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/articles", response_model=ArticlesPage)
async def get_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    source_name: Optional[str] = None,
):
    """Get articles with filters and pagination"""
    try:
        db = PostgresConnector(config.POSTGRES_CONFIG, OPENAI_API_KEY)
        articles, total = db.get_articles_filtered(
            page=page,
            page_size=page_size,
            source_name=source_name
        )
        return ArticlesPage(
            total=total,
            page=page,
            page_size=page_size,
            articles=articles
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/articles/search")
async def semantic_search(request: SearchRequest):
    """Search articles semantically and get AI response"""
    try:
        db = PostgresConnector(config.POSTGRES_CONFIG, OPENAI_API_KEY)
        relevant_articles = db.semantic_search(
            prompt=request.prompt, 
            limit=request.limit,
            published_after=request.published_after,
            published_before=request.published_before
        )
        if len(relevant_articles) == 0:
            return {"answer": "No relevant articles found in the database for the given date range", "sources": []}

        # Prepare context from relevant articles
        context = "\n\n".join([
            f"Title: {article['title']}\nContent: {article['content']}"
            for article in relevant_articles
        ])

        # Get AI response
        response = client.chat.completions.create(
            model=request.model,
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": f"Based on these news articles:\n\n{context}\n\nAnswer this question: {request.prompt}"}
            ]
        )

        return {
            "answer": response.choices[0].message.content,
            "sources": list({
                (
                    article["sourcename"],
                    article["sourceurl"],
                ): {
                    "source_name": article["title"],
                    "source_url": article["articleurl"],
                }
                for article in relevant_articles
                if article["title"] is not None
            }.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/execute-sql")
async def execute_sql(
    request: SearchRequest
):
    try:
        db = PostgresConnector(config.POSTGRES_CONFIG, OPENAI_API_KEY)
        db_uri = f"postgresql://{config.POSTGRES_CONFIG['user']}:{config.POSTGRES_CONFIG['password']}@{config.POSTGRES_CONFIG['host']}:{config.POSTGRES_CONFIG['port']}/{config.POSTGRES_CONFIG['database']}"
        
        sql_db = SQLDatabase.from_uri(
            db_uri,
            include_tables=['articles'],
            view_support=True,
            custom_table_info={
                "articles": """
                Table articles contains crypto news with columns:
                - id: unique identifier
                - title: article title (use for text search)
                - content: full article content (use for text search)
                - publishedat: publication date (timestamp)
                - sourcename: name of the news source
                - sourceurl: URL of the news source
                - articleurl: direct link to the article
                
                Example queries:
                1. Recent news about Bitcoin:
                   SELECT title, content, publishedat, articleurl 
                   FROM articles 
                   WHERE (title ILIKE '%bitcoin%' OR content ILIKE '%bitcoin%')
                   ORDER BY publishedat DESC LIMIT 10
                
                2. News from specific source:
                   SELECT title, content, publishedat, articleurl 
                   FROM articles 
                   WHERE sourcename ILIKE '%coindesk%'
                   ORDER BY publishedat DESC LIMIT 10
                
                3. Multiple keyword search:
                   SELECT title, content, publishedat, articleurl 
                   FROM articles 
                   WHERE (title ILIKE '%eth%' OR content ILIKE '%ethereum%')
                   ORDER BY publishedat DESC LIMIT 10
                """
            }
        )
        
        llm = ChatOpenAI(api_key=OPENAI_API_KEY, temperature=0)
        chain = create_sql_query_chain(llm, sql_db)
        
        sql_prompt = f"""
        Generate a PostgreSQL query for the following question: "{request.prompt}"

        Requirements:
        1. ALWAYS return these columns: title, content, publishedat, articleurl
        2. Use ILIKE for case-insensitive text search in both title AND content
        3. Include relevant WHERE clauses based on the question
        4. ALWAYS include ORDER BY publishedat DESC
        5. ALWAYS limit results to 10 records
        6. Use proper PostgreSQL syntax
        7. Consider synonyms and related terms in search
        8. Handle multiple keywords if present
        
        Example format:
        SELECT title, content, publishedat, articleurl
        FROM articles
        WHERE (title ILIKE '%keyword1%' OR content ILIKE '%keyword1%')
          AND (title ILIKE '%keyword2%' OR content ILIKE '%keyword2%')
        ORDER BY publishedat DESC
        LIMIT 10
        """
        
        sql_query = chain.invoke({"question": sql_prompt})
        
        with db.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql_query)
            relevant_articles = [dict(row) for row in cur.fetchall()]
        
        if not relevant_articles:
            no_results_response = client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": f"I couldn't find any articles about '{request.prompt}'. Please suggest some alternative search terms or topics that might be more relevant to crypto news."}
                ]
            )
            
            return {
                "answer": no_results_response.choices[0].message.content,
                "sources": [],
                "sql_query": sql_query,
                "found_results": False
            }
        
        context = "\n\n".join([
            f"Title: {article['title']}\nDate: {article['publishedat']}\nContent: {article['content']}"
            for article in relevant_articles
        ])
        
        response = client.chat.completions.create(
            model=request.model,
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": f"Based on these news articles:\n\n{context}\n\nAnswer this question: {request.prompt}"}
            ]
        )
        
        sources = list({
            (
                article["title"],
                article["articleurl"],
            ): {
                "source_name": article["title"],
                "source_url": article["articleurl"],
            }
            for article in relevant_articles
            if article["title"] is not None
        }.values())
        
        return {
            "answer": response.choices[0].message.content,
            "sources": sources,
            "sql_query": sql_query,
            "found_results": True
        }
    except Exception as e:
        error_response = client.chat.completions.create(
            model=request.model,
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": f"There was an error processing your query about '{request.prompt}'. The error was: {str(e)}. Please try rephrasing your question or being more specific."}
            ]
        )
        
        return {
            "answer": error_response.choices[0].message.content,
            "sources": [],
            "sql_query": str(e),
            "found_results": False,
            "error": str(e)
        }
    finally:
        db.close() 