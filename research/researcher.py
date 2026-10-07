from research.search import search_web
from research.sources import open_source


def research(query, result_count=5, open_count=3):
    results = search_web(query, result_count)
    sources = []
    for result in results[:open_count]:
        text = result.get("text", "")
        if not text:
            try:
                text = open_source(result["url"])
            except Exception as error:
                text = "Could not open source: {}".format(error)
        sources.append({**result, "text": text})
    return {"query": query, "results": results, "sources": sources}


def format_research_context(report):
    lines = ["Research query: {}".format(report["query"]), ""]
    for index, source in enumerate(report["sources"], 1):
        lines.extend([
            "Source {}: {}".format(index, source.get("title", "")),
            "URL: " + source.get("url", ""),
            source.get("text", "")[:5000],
            "",
        ])
    return "\n".join(lines)
