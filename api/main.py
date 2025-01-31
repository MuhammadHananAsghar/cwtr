from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel, Field
from psycopg2.extras import DictCursor
from langchain.sql_database import SQLDatabase
from langchain.chat_models import ChatOpenAI
from langchain.chains import create_sql_query_chain

client = OpenAI()
from db.postgres_connector import PostgresConnector
import config

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
        db = PostgresConnector(config.POSTGRES_CONFIG, config.OPENAI_API_KEY)
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
        db = PostgresConnector(config.POSTGRES_CONFIG, config.OPENAI_API_KEY)
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
        db = PostgresConnector(config.POSTGRES_CONFIG, config.OPENAI_API_KEY)
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
                    "source_name": article["sourcename"],
                    "source_url": article["sourceurl"],
                }
                for article in relevant_articles
                if article["sourcename"] is not None
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
        db = PostgresConnector(config.POSTGRES_CONFIG, config.OPENAI_API_KEY)
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        # Setup LangChain for SQL generation
        db_uri = f"postgresql://{config.POSTGRES_CONFIG['user']}:{config.POSTGRES_CONFIG['password']}@{config.POSTGRES_CONFIG['host']}:{config.POSTGRES_CONFIG['port']}/{config.POSTGRES_CONFIG['database']}"
        sql_db = SQLDatabase.from_uri(
            db_uri,
            include_tables=['articles'],
            view_support=True,
            custom_table_info={
                "articles": """
                Table articles columns:
                id, slug, title, content, clean_content, publishedat, authorname, 
                category, sourcename, sourceurl, imageurl, articleurl, tags, 
                createdat, updatedat
                """
            }
        )
        
        llm = ChatOpenAI(api_key=config.OPENAI_API_KEY, temperature=0)
        chain = create_sql_query_chain(llm, sql_db)
        
        # Generate SQL query
        sql_query = chain.invoke({
            "question": f"""
            Generate a PostgreSQL query for: {request.prompt}
            Return these columns: id, title, content, publishedat, sourcename, sourceurl
            Use ILIKE for text search and limit to 5 results
            """
        })
        
        # Execute the generated query
        with db.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql_query)
            relevant_articles = [dict(row) for row in cur.fetchall()]
        
        if not relevant_articles:
            no_results_response = client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant explaining search results."},
                    {"role": "user", "content": f"No articles were found for: {request.prompt}"}
                ]
            )
            
            return {
                "answer": no_results_response.choices[0].message.content,
                "sources": [],
                "sql_query": sql_query,
                "found_results": False
            }
        
        context = "\n\n".join([
            f"Title: {article['title']}\nContent: {article['content']}"
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
                article["sourcename"],
                article["sourceurl"],
            ): {
                "source_name": article["sourcename"],
                "source_url": article["sourceurl"],
            }
            for article in relevant_articles
            if article["sourcename"] is not None
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
                {"role": "system", "content": "You are a helpful assistant explaining errors."},
                {"role": "user", "content": f"An error occurred: {str(e)}"}
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