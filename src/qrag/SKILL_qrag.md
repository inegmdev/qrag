---
name: qrag
description: Search the local RAG database to answer questions about code or documentation. Use when the user asks about code, functions, symbols, API usage, or technical documentation from the indexed codebase.
---

Search the local RAG database iteratively to answer a question about code or documentation.

## Database scoping (do this first)

Multiple databases can be globally active at once (`qrag ai active`), but searching all of
them on every query floods you with irrelevant results and increases the chance of a wrong
answer. Narrow the scope for this conversation before searching:

1. **At the start of a conversation**, or **whenever the user asks to change what's searched**
   (e.g. "just look in the RTOS docs", "search everything again"): call `list_databases` to see
   the globally active set, present it to the user as an interactive multi-select checklist
   (arrow keys + spacebar, one item per database), and call `set_active_databases` with their
   selection. If the user wants everything again, call `reset_active_databases` instead of
   re-selecting every item.
2. If a database has only one entry globally active, skip the checklist — there's nothing to
   narrow.
3. If any tool response includes a `scope_hint` field, it means this session hasn't been scoped
   yet — treat it as a one-time nudge to run step 1, then proceed with the user's query using the
   full result already returned (don't discard it or re-run the search).
4. If a tool response includes an `excluded_active_dbs` field, those are databases the user has
   approved globally but excluded from this session's scope. If the results seem thin or
   off-target, look at those names/tags yourself and judge whether one might hold the answer —
   if so, tell the user and offer to activate it (via `set_active_databases`). Do not silently
   search them yourself; only the user's selection changes what gets searched.
5. **Keep the user informed**: briefly mention when you scope, re-scope, or reset the session's
   active databases, so background changes to search scope are never silent.

## Workflow

Given: $ARGUMENTS (your question or topic)

1. **Think first**: Decompose the question — what concept am I looking for in docs? What symbol/function in code? Write your search intent before calling tools.

2. **Search in parallel**: Call `search_docs` and `search_code` (both MCP tools) simultaneously with targeted queries. If only docs or only code apply, search only what is relevant.

3. **Assess results**: For each result set, note the similarity scores and excerpt relevance. State explicitly what you found and what remains unanswered.

4. **Iterate if needed**: Refine your query and search again. Stop iterating when:
   - You have a high-confidence answer with supporting evidence, OR
   - Two consecutive rounds return no new information (low scores, repeated results), OR
   - The topic is clearly outside the indexed content.

5. **Check in with the user** every 2–3 rounds: briefly state what you have found so far and ask if you should continue or refocus.

6. **If information is not found**: Tell the user the topic is not in the local database. Suggest searching online and offer to help index new content with `qrag build -i <path>`.
   - **CRITICAL**: Do NOT use `search_web`, `read_url_content`, or any other external web access tools. You must strictly limit all operations to the local index.

7. **Conclude**: Synthesize all findings into a clear answer. Cite source file paths, symbol names, doc sections, and page numbers. Flag any inconsistencies between docs and code.

## Constraints & Guardrails
- **PROHIBITED**: Under no circumstances should you call the `search_web` tool, `read_url_content` tool, or any other web-based search/scraping tools. If the local search returns no results or insufficient information, you must report this limitation directly to the user (per step 6) instead of searching the web yourself.

## Available MCP tools
- `search_code(query)` — semantic search over indexed code symbols (returns top 10)
- `search_docs(query)` — semantic search over indexed documentation (returns top 10)
- `list_symbols(pattern)` — list code symbols matching a glob pattern
- `get_symbol(name)` — retrieve full source of a specific symbol
- `list_databases()` — list globally active databases available to scope this session to
- `set_active_databases(versions)` — narrow this session's search to the given subset (session-only, does not change global config)
- `reset_active_databases()` — clear session narrowing, revert to the full globally active set
