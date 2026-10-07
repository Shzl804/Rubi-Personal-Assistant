import re

from memory.long_term import propose_memory


SENSITIVE_WORDS = {
    "password", "api key", "api_key", "token", "secret",
    "private key", "credit card",
}


def extract_candidate(text, topic=None, project=None):
    cleaned = str(text).strip()
    lowered = cleaned.lower()
    if not cleaned or any(word in lowered for word in SENSITIVE_WORDS):
        return None
    match = re.search(
        r"(?:remember that|remember this|don't forget that)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return {
        "content": match.group(1).strip().rstrip("."),
        "category": "preference",
        "topic": topic,
        "project": project,
        "confidence": 0.95,
    }


def propose_from_user_text(text, topic=None, project=None):
    candidate = extract_candidate(text, topic, project)
    if not candidate:
        return None
    candidate["id"] = propose_memory(
        candidate["content"], candidate["category"], candidate["topic"],
        candidate["project"], candidate["confidence"], "explicit_request",
    )
    return candidate
