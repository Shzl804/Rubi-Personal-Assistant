import json
import os
import urllib.request


SEARCH_URL = "https://api.tavily.com/search"


def search_web(query, count=5):
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY is missing. Add it to .env to use web research."
        )
    payload = json.dumps({
        "query": str(query),
        "search_depth": "advanced",
        "max_results": max(1, min(int(count), 10)),
        "include_answer": False,
        "include_raw_content": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        SEARCH_URL,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            "User-Agent": "Rubi-Assistant/Stage5",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("content", ""),
            "text": item.get("raw_content") or item.get("content", ""),
            "published_date": item.get("published_date", ""),
        }
        for item in data.get("results", [])
    ]
