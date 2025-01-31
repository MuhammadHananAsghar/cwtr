import sys
from pathlib import Path
import requests

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

import streamlit as st
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import DictCursor
from openai import OpenAI
import config
from langchain_openai import ChatOpenAI
from langchain.chains import create_sql_query_chain
from langchain_community.utilities import SQLDatabase

def get_total_articles():
    """Get total number of articles from the API"""
    try:
        response = requests.get("http://31.220.109.45/articles/count")
        if response.status_code == 200:
            return response.json()["total_articles"]
    except Exception as e:
        st.error(f"Error fetching article count: {e}")
    return 0

def setup_langchain():
    db_uri = f"postgresql://{config.POSTGRES_CONFIG['user']}:{config.POSTGRES_CONFIG['password']}@{config.POSTGRES_CONFIG['host']}:{config.POSTGRES_CONFIG['port']}/{config.POSTGRES_CONFIG['database']}"
    
    db = SQLDatabase.from_uri(
        db_uri,
        include_tables=['articles'],
        view_support=True,
        custom_table_info={
            "articles": """
            Table articles columns:
            id, slug, title, content, clean_content, publishedat, authorname, 
            category, sourcename, sourceurl, imageurl, articleurl, tags, 
            createdat, updatedat
            
            Example queries:
            - Search by title: SELECT * FROM articles WHERE title ILIKE '%search_term%'
            - Filter by source: SELECT * FROM articles WHERE sourcename = 'source'
            - Recent articles: SELECT * FROM articles ORDER BY publishedat DESC
            """
        }
    )
    
    llm = ChatOpenAI(api_key=config.OPENAI_API_KEY, temperature=0)
    chain = create_sql_query_chain(llm, db)
    
    return db, chain

def generate_sql_query(chain, user_prompt: str, system_context: str) -> str:
    full_prompt = f"""
    Context: {system_context}
    Question: {user_prompt}
    
    Generate a PostgreSQL query that:
    1. Uses appropriate WHERE clauses with ILIKE for text search
    2. Always includes ORDER BY and LIMIT clauses
    3. Returns these columns: id, title, content, publishedat, sourcename, sourceurl
    4. Uses exact column names (all lowercase)
    5. Limits results to 5 records
    """
    
    try:
        sql_query = chain.invoke({"question": full_prompt})
        return sql_query
    except Exception as e:
        st.error(f"Error generating SQL: {e}")
        return None

def execute_search(prompt: str, system_prompt: str, model: str):
    try:
        db, chain = setup_langchain()
        sql_query = generate_sql_query(chain, prompt, system_prompt)
        if not sql_query:
            return None
            
        response = requests.post(
            "http://localhost:8000/execute-sql",
            json={
                "prompt": prompt,
                "system_prompt": system_prompt,
                "model": model,
                "sql_query": sql_query
            }
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error: {response.text}")
            return None
        
    except Exception as e:
        st.error(f"Error in search: {e}")
        return None

def main():
    st.set_page_config(
        page_title="Crypto News Search",
        page_icon="🔍",
        layout="wide"
    )

    total_articles = get_total_articles()
    st.title("🔍 Crypto News Search")
    st.markdown(f"*Searching across **{total_articles:,}** articles from multiple sources*")

    with st.sidebar:
        st.header("Settings")
        model = st.selectbox(
            "Select Model",
            ["gpt-4o-mini", "gpt-4o", "chatgpt-4o-latest", "gpt-4o-realtime-preview", "gpt-4-turbo", "gpt-3.5-turbo"],
            index=0
        )
        system_prompt = st.text_area(
            "System Prompt",
            value="You are a helpful assistant that provides insights based on crypto news articles.",
            height=100
        )

    st.subheader("Search Crypto News")
    user_prompt = st.text_area("Enter your question", height=100)

    if st.button("Search", type="primary"):
        if user_prompt:
            with st.spinner("Searching and analyzing news articles..."):
                try:
                    result = execute_search(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        model=model
                    )
                    
                    if result:
                        with st.expander("View Generated SQL Query"):
                            st.code(result["sql_query"], language="sql")
                        
                        st.markdown("### Answer")
                        st.markdown(result["answer"])
                        
                        if result.get("found_results", False):
                            st.markdown("### Sources")
                            for source in result["sources"]:
                                st.markdown(
                                    f"- [{source['source_name']}]({source['source_url']})"
                                )
                        
                        if result.get("error"):
                            st.error(f"Original error: {result['error']}")
                            
                except Exception as e:
                    st.error(f"Error occurred: {str(e)}")
        else:
            st.warning("Please enter a question")

    st.markdown("---")
    st.markdown("Made with ❤️ by Muhammad")

if __name__ == "__main__":
    main()