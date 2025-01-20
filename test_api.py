import requests

response = requests.post(
    "http://31.220.109.45/articles/search",
    json={
        "prompt": "What are the latest developments in Bitcoin ETFs?",
        "system_prompt": "You are a helpful assistant that provides insights based on crypto news articles.",
        "model": "gpt-4o-mini",
    },
)
if response.status_code == 200:
    data = response.json()
    print(data)
else:
    print(f"Request failed with status code {response.status_code}")
    print(response.text)
