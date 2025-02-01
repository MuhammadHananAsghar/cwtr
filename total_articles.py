import requests

response = requests.get("http://localhost:8000/articles/count")
print(response.json())
