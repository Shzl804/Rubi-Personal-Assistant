from memory.long_term import search_memories


def find_suggestion(query, topic=None, project=None):
    memories = search_memories(query, topic, project, limit=1)
    if not memories:
        return None
    return "A possibly relevant past memory is: {}".format(memories[0]["content"])
