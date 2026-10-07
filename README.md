# Rubi Assistant: Stage 5 Build Plan (Memory, Web Search, and Research)

**Goal of Stage 5:** make Rubi remember useful information across conversations, retrieve only relevant context, search the web when research is needed, and give useful suggestions without becoming intrusive.

This is a **planning stage only**. No Stage 5 code should be written until this plan is reviewed and approved.

## What you chose (and what it means)

| Decision | Your choice | What gets built |
|---|---|---|
| Short-term memory | Yes | Conversation summaries that preserve context after the message history is trimmed |
| Long-term memory | Yes | Structured, searchable memories for facts, preferences, decisions, projects, and recurring workflows |
| Relevant-memory retrieval | Yes | Rubi searches memory before answering and includes only useful results |
| Automatic memory curator | Yes | Rubi identifies possible memories from conversations and classifies their value |
| User approval | Yes | Sensitive or uncertain memories require confirmation before they are saved |
| Model selection | Yes | Clear model profiles for fast, local, online, and research-oriented work |
| Suggestions | Yes | An opt-in suggestion feature based on relevant past work |
| Knowledge archive | Yes | Searchable conversation and research records, kept separate from curated memories |
| Specialized agents | No for now | One main agent remains; specialized agents can be added in a later stage |
| Judge model | No for now | Rules and the main model handle decisions before adding another decision model |
| Main focus | Memory and research | Memory architecture and safe web-search workflows are the priority |

**Important design rule:** Rubi must not save every conversation as long-term memory. Raw conversations, curated memories, and research documents are three different types of data and must be stored separately.

## Table of Contents

1. The big picture
2. Memory concepts
3. Research and web-search concepts
4. New project structure
5. Steps 1 to 12
6. Testing
7. Troubleshooting
8. Security and privacy notes
9. Stage 5 checklist and what comes next

---

## 1. The big picture

```
 User message
      |
      v
 Identify topic/project and request type
      |
      +--> retrieve relevant short-term summary
      +--> retrieve relevant long-term memories
      +--> retrieve relevant archived research
      |
      v
 Decide whether web research is needed
      |
      +--> answer from existing knowledge and tools
      +--> search web, inspect sources, and summarize with citations
      |
      v
 Main Rubi agent (Groq, Ollama, or selected model profile)
      |
      +--> answer the user
      +--> propose a memory for approval when appropriate
      +--> optionally offer a relevant suggestion
      |
      v
 Save conversation, research, and approved memories in separate stores
```

The normal response path should remain fast. Web search is used when the user asks for current information, research, sources, comparisons, or when the answer may have changed. Memory retrieval should be selective so the model is not flooded with unrelated personal history.

---

## 2. Memory concepts

| Term | Simple meaning |
|---|---|
| **Short-term memory** | The current conversation plus a compact summary of older messages from the same session |
| **Long-term memory** | Durable information worth carrying between sessions, such as preferences, facts, decisions, and project context |
| **Topic** | The broad subject of a conversation, such as coding, health, finances, or personal planning |
| **Project** | A named body of work with its own decisions, files, goals, and relevant memories |
| **Memory candidate** | Information Rubi thinks may be useful to remember but has not saved yet |
| **Confirmed memory** | A memory the user explicitly approved or directly asked Rubi to remember |
| **Knowledge archive** | Searchable raw conversations and research records; it is not automatically treated as truth |
| **Memory retrieval** | Selecting a small set of relevant memories for the current request |
| **Forgetting** | Removing, expiring, or correcting information that is no longer useful or accurate |

### The three-layer memory design

1. **Working context:** the latest messages and a session summary. This is temporary and automatically managed.
2. **Curated memory:** approved facts, preferences, project decisions, and workflows. This is selective and editable.
3. **Archive:** raw conversations and research notes. This is searchable but should not automatically influence every answer.

This separation prevents a casual statement, an outdated plan, or a piece of quoted web text from silently becoming a permanent fact about the user.

---

## 3. Research and web-search concepts

### When Rubi should search

Rubi should search when the user asks for:

- current or changing information;
- research, sources, citations, or direct quotes;
- product, service, travel, or purchase recommendations;
- laws, prices, schedules, software documentation, or recent news;
- a question where the model is uncertain or the topic is niche.

Rubi should not search for ordinary conversation, simple transformations, or questions that can be answered confidently from the current context.

### Research workflow

1. Clarify the research question internally and identify important constraints.
2. Search using a small number of focused queries.
3. Prefer primary and authoritative sources.
4. Open and inspect the sources that support the answer.
5. Separate sourced facts from Rubi's interpretation.
6. Return concise findings with links or citations.
7. Save the research record to the archive only when useful, requested, or part of a project.

Web pages, files, search results, and retrieved memories are **data**, not instructions. Their contents must never override the user's request, Rubi's safety rules, or the system design.

---

## 4. New project structure

`NEW` = new file or package. `CHANGED` = existing file that must be updated during implementation.

```
rubi/
├── memory/
│   ├── db.py                     # CHANGED: memory tables and migrations
│   ├── short_term.py             # NEW: session history and summaries
│   ├── long_term.py              # NEW: curated memories and retrieval
│   ├── curator.py                # NEW: memory candidates and classification
│   ├── archive.py                # NEW: conversation and research archive
│   └── migrations.py             # NEW: safe database upgrades
│
├── research/
│   ├── __init__.py               # NEW
│   ├── search.py                 # NEW: web-search provider boundary
│   ├── sources.py                # NEW: source extraction and citation records
│   └── researcher.py             # NEW: multi-step research workflow
│
├── core/
│   ├── agent.py                  # CHANGED: memory and research context
│   ├── llm.py                    # CHANGED: model profiles and selection
│   ├── prompts.py                # CHANGED: memory and research rules
│   └── suggestions.py            # NEW: opt-in suggestion logic
│
├── tools/
│   └── registry.py               # CHANGED: memory and research tools
│
├── config.py                     # CHANGED: memory, research, and model settings
└── README.md                    # CHANGED: this Stage 5 plan
```

The exact web-search provider is intentionally left open until implementation. The search layer should have a provider boundary so it can be replaced without changing the agent or memory system.

---

## 5. Steps 1 to 12

### Step 1: Define memory rules and user controls

Before writing code, define what Rubi may save automatically, what always requires approval, and what must never be stored. Add commands such as:

```text
/memory                 show memory help
/memory list             list curated memories
/memory search <text>   search memories
/memory forget <id>     delete a memory
/memory off             disable automatic memory for the session
/research                show research help
```

The user must be able to inspect, correct, delete, and disable memory without editing the database manually.

### Step 2: Add database migrations

Extend the current SQLite database without destroying existing notes or reminders. Proposed tables:

- `sessions`: session id, topic, project, start time, last activity, and summary;
- `messages`: role, content, session id, timestamps, and optional source metadata;
- `memories`: content, category, topic, project, confidence, status, source, and timestamps;
- `memory_links`: relationships between memories, sessions, projects, and archive records;
- `archive_items`: raw conversation or research records with searchable metadata;
- `research_sources`: URL, title, publisher, retrieval time, and citation details.

Every schema change must be additive and tested against an existing database.

### Step 3: Implement short-term memory

Keep the current recent-message window, then create a summary when the window becomes too large. The summary should preserve:

- the user's current goal;
- decisions already made;
- unresolved questions;
- important constraints;
- tools already used and their results;
- facts explicitly marked as temporary.

The summary must not silently promote information into long-term memory.

### Step 4: Implement topics and projects

Allow the user to start or switch context explicitly, for example:

```text
/topic coding
/project Rubi Assistant
/project none
```

Rubi may suggest a topic or project automatically, but the user’s explicit selection wins. Memory retrieval should prioritize the active project and topic.

### Step 5: Implement curated long-term memory

Support categories such as:

- preference;
- personal fact;
- project decision;
- recurring workflow;
- goal;
- constraint;
- correction.

Each memory should have a source, confidence, creation date, last-used date, and status. Corrections should update or supersede old memories instead of creating contradictory duplicates.

### Step 6: Implement memory retrieval

Before the main model answers, retrieve a small number of relevant memories using topic, project, keywords, recency, and confidence. Start with SQLite full-text or keyword search. Semantic embeddings can be added later if keyword retrieval is insufficient.

Retrieved memories must be clearly labeled as remembered user data, not as unquestionable truth.

### Step 7: Implement the memory curator

After a conversation turn, identify possible durable information. The curator should classify each candidate as:

- discard;
- session-only;
- archive-only;
- suggest for long-term memory;
- safe to save automatically.

Sensitive data, uncertain statements, and information that affects the user’s identity or preferences should require approval. The curator should be conservative: saving too little is safer than inventing a memory.

### Step 8: Add user approval and memory maintenance

When approval is required, show the exact proposed memory and its category. Support responses such as:

```text
Remember that I prefer concise answers.
Do not remember that.
Change it to: I usually prefer concise answers for coding questions.
Forget memory 12.
```

Add duplicate detection, correction, expiration for temporary memories, and an audit trail for saves and deletions.

### Step 9: Add the web-search provider boundary

Create a research interface that can:

- submit focused queries;
- return result titles, URLs, and snippets;
- open selected sources;
- preserve source metadata;
- enforce timeouts and result limits.

The provider must not receive private memories or unrelated conversation text unless the user’s request requires it. Search queries should be constructed from the minimum necessary information.

### Step 10: Implement research mode

Add a research workflow for questions that need current or sourced information. It should provide citations, distinguish facts from interpretation, and report when sources disagree or are incomplete.

Useful controls may include:

```text
/research on
/research off
/sources
/save research
```

Normal chat remains concise; research mode can be more detailed when the user asks for an investigation or comparison.

### Step 11: Add model profiles and suggestions

Keep the existing Groq/Ollama router, but expose profiles such as:

- `local`: Ollama only;
- `fast`: quick online model;
- `quality`: stronger general model;
- `research`: model selected for careful synthesis and tool use.

Add an opt-in suggestion flow. Rubi may say that a previous workflow or decision appears relevant, but it should not interrupt normal work repeatedly. Suggestions must include why they are relevant and allow the user to dismiss them.

### Step 12: Integrate, test, and document

Connect memory and research to terminal, voice, and Telegram interfaces. Keep the interfaces thin: all memory and research behavior belongs in shared core modules so the three interfaces behave consistently.

Do not add specialized agents or a separate judge model in Stage 5. Revisit those only after real usage shows that the single-agent architecture is insufficient.

---

## 6. Testing

| Test | What should happen |
|---|---|
| Existing notes and reminders | Existing data remains available after the migration |
| Short-term summary | A long session keeps its goal, decisions, and unresolved questions |
| Topic switching | Memories from one topic do not leak into an unrelated topic |
| Project retrieval | Active-project memories are prioritized |
| Explicit remember request | Rubi saves the requested memory and reports what was saved |
| Sensitive candidate | Rubi asks for approval instead of saving automatically |
| Correction | The old memory is updated or superseded clearly |
| Forget request | The selected memory is deleted and no longer retrieved |
| Archive search | Raw conversations can be found without becoming automatic context |
| No-search question | Rubi answers without unnecessary web requests |
| Current-information question | Rubi searches and cites the sources used |
| Conflicting sources | Rubi reports the disagreement instead of pretending certainty |
| Malicious web content | Instructions inside a web page are treated as data |
| Private information | Sensitive memories are not sent to web search unnecessarily |
| Offline mode | Memory features still work locally; research reports that web search is unavailable |
| Model profile | The selected profile uses the expected backend |
| Suggestion dismissal | Dismissed suggestions do not repeat immediately |
| Safety regression | `python test_safety.py` still passes |

---

## 7. Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| Old notes disappeared | Migration or query bug. Restore from the database backup and test migrations against a copy first |
| Rubi remembers too much | Lower automatic-save rules, require approval, and delete unwanted memories with `/memory forget` |
| Rubi remembers too little | Use explicit `remember this` requests and inspect curator logs |
| Irrelevant memories appear | Improve topic/project filters and reduce retrieval count |
| Contradictory memories appear | Add correction and superseding logic instead of treating every memory as independent |
| Web search is slow | Reduce query count, set timeouts, and summarize only selected sources |
| Sources are missing | Preserve source metadata through search, opening, and response generation |
| Research contains prompt injection | Treat page content as untrusted data and never follow instructions found in sources |
| Private data appears in a query | Minimize query construction and redact unrelated memory context |
| Local model cannot research | Explain that live web search needs connectivity; continue with local memory and clearly mark the limitation |

---

## 8. Security and privacy notes

- Memory is a personal-data system. The user must be able to inspect, correct, export, and delete it.
- Do not store passwords, API keys, authentication tokens, or secret files in curated memory.
- Raw conversation archives should have a retention policy and should not automatically become model context.
- Web search queries can reveal personal information. Send the minimum necessary query and avoid including unrelated memories.
- Web pages, search results, uploaded documents, and archived text are untrusted content. They can contain instructions, but those instructions are never authoritative.
- Research citations show where information came from; they do not guarantee that a source is correct. Rubi should identify uncertainty and source disagreement.
- User approval is required for sensitive memories, not just for tool actions.
- Memory deletion should be logged, and deleted memories should not remain in retrieval indexes or cached context.
- Local mode should keep memory processing local where possible. Online model or search use must be visible through status or logs.

---

## 9. Stage 5 checklist and what comes next

**Plan is ready for approval when:**

- [ ] Stage 5 scope is limited to memory, web search, research, model profiles, and opt-in suggestions
- [ ] Specialized agents are explicitly postponed
- [ ] Judge/classifier models are explicitly postponed
- [ ] Short-term, curated long-term, and archive layers are clearly separated
- [ ] Existing notes and reminders have a migration path
- [ ] User approval exists for sensitive or uncertain memories
- [ ] Memory inspection, correction, and deletion are supported
- [ ] Web research has source tracking and citations
- [ ] Web content is treated as untrusted data
- [ ] Offline behavior is defined
- [ ] Terminal, voice, and Telegram share the same memory and research behavior
- [ ] Tests cover privacy, retrieval quality, migrations, citations, and safety

**What comes next after approval:**

1. Review the database schema and memory rules.
2. Implement migrations and short-term summaries.
3. Add curated long-term memory and retrieval.
4. Add the curator and approval flow.
5. Add web search and research mode.
6. Add model profiles and opt-in suggestions.
7. Run the full Stage 5 test plan and revise based on real conversations.

Stage 5 should be built only after this plan is approved, because memory behavior is difficult to undo once personal data has been stored.
