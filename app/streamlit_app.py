import streamlit as st
import requests
import markdown

def main():
    # Set page config
    st.set_page_config(
        page_title="Crypto News Search",
        page_icon="🔍",
        layout="wide"
    )

    # Title
    st.title("🔍 Crypto News Semantic Search")

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
                    # Make API request
                    response = requests.post(
                        "http://31.220.109.45/articles/search",
                        json={
                            "prompt": user_prompt,
                            "system_prompt": system_prompt,
                            "model": model,
                        },
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