from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel, Field

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
    system_prompt: str = Field(default="You are a helpful assistant that provides insights based on crypto news articles.")
    prompt: str
    model: str = Field(default="gpt-4o-mini")
    limit: int = Field(default=5, ge=1, le=20)

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
        relevant_articles = db.semantic_search(request.prompt, request.limit)

        # Prepare context from relevant articles
        context = "\n\n".join([
            f"Title: {article['title']}\nContent: {article['content']}"
            for article in relevant_articles
        ])

        # Get AI response
        response = client.chat.completions.create(model=request.model,
        messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": f"Based on these news articles:\n\n{context}\n\nAnswer this question: {request.prompt}"}
        ])

        return {
            "answer": response.choices[0].message.content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close() 