import streamlit as st
import requests
import markdown
from datetime import datetime, timedelta, timezone

def get_total_articles():
    """Get total number of articles from the API"""
    try:
        response = requests.get("http://31.220.109.45/articles/count")
        if response.status_code == 200:
            return response.json()["total_articles"]
    except Exception as e:
        st.error(f"Error fetching article count: {e}")
    return 0

def main():
    # Set page config
    st.set_page_config(
        page_title="Crypto News Search",
        page_icon="🔍",
        layout="wide"
    )

    # Get total articles count
    total_articles = get_total_articles()

    # Title with article count
    st.title("🔍 Crypto News Semantic Search")
    st.markdown(f"*Total **{total_articles:,}** articles in the database from multiple sources*")

    # Sidebar for model selection and system prompt
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
        
        # Date filters
        st.subheader("Date Filters (Optional)")
        
        # Add a checkbox to enable/disable date filters
        use_date_filter = st.checkbox("Filter by date", value=False)
        
        if use_date_filter:
            # Default date range: last 30 days
            default_end_date = datetime.now(timezone.utc)
            default_start_date = default_end_date - timedelta(days=30)
            
            # From datetime selection
            st.write("From (UTC):")
            from_cols = st.columns([7, 3])
            with from_cols[0]:
                start_date = st.date_input(
                    "##",
                    value=default_start_date.date(),
                    max_value=datetime.now(timezone.utc).date(),
                    label_visibility="collapsed"
                )
            with from_cols[1]:
                start_time = st.time_input(
                    "##",
                    value=datetime.strptime("00:00", "%H:%M").time(),
                    label_visibility="collapsed"
                )
            
            # To datetime selection
            st.write("To (UTC):")
            to_cols = st.columns([7, 3])
            with to_cols[0]:
                end_date = st.date_input(
                    "###",
                    value=default_end_date.date(),
                    max_value=datetime.now(timezone.utc).date(),
                    label_visibility="collapsed"
                )
            with to_cols[1]:
                end_time = st.time_input(
                    "###",
                    value=datetime.strptime("23:59", "%H:%M").time(),
                    label_visibility="collapsed"
                )
            
            # Combine date and time into UTC datetime
            published_after = datetime.combine(start_date, start_time, tzinfo=timezone.utc)
            published_before = datetime.combine(end_date, end_time, tzinfo=timezone.utc)
            
            # Display selected UTC time
            st.caption(f"Selected range: {published_after.strftime('%Y-%m-%d %H:%M')} to {published_before.strftime('%Y-%m-%d %H:%M')} UTC")
        else:
            published_after = None
            published_before = None

    # Main content
    st.subheader("Search Crypto News")

    # User prompt input
    user_prompt = st.text_area("Enter your question", height=100)

    # Search button
    if st.button("Search", type="primary"):
        if user_prompt:
            # Show spinner while processing
            with st.spinner("Searching and analyzing news articles..."):
                try:
                    # Prepare request payload
                    payload = {
                        "prompt": user_prompt,
                        "system_prompt": system_prompt,
                        "model": model,
                    }
                    
                    # Add date filters if enabled
                    if use_date_filter:
                        payload["published_after"] = published_after.isoformat()
                        payload["published_before"] = published_before.isoformat()
                    
                    # Make API request
                    response = requests.post(
                        "http://31.220.109.45/articles/search",
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Display answer in a nice box
                        st.markdown("### Answer")
                        st.markdown(data["answer"])
                        
                        # Display sources
                        st.markdown("### Sources")
                        for source in data["sources"]:
                            st.markdown(
                                f"- [{source['source_name']}]({source['source_url']})"
                            )
                            
                        # Display date range if used
                        if use_date_filter:
                            st.markdown("---")
                            st.markdown("### Search Parameters")
                            st.markdown(f"Date Range: {published_after.strftime('%Y-%m-%d %H:%M')} to {published_before.strftime('%Y-%m-%d %H:%M')} UTC")
                    else:
                        st.error(f"Error: {response.status_code}")
                        st.code(response.text)
                        
                except Exception as e:
                    st.error(f"Error occurred: {str(e)}")
        else:
            st.warning("Please enter a question")

    # Footer
    st.markdown("---")
    st.markdown("Made with ❤️ by Muhammad")

if __name__ == "__main__":
    main() 