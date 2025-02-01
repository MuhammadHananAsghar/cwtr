import requests

response = requests.get("http://31.220.109.45/articles/count")
print(response.json())
