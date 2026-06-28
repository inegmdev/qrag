---
name: qrag
description: Search the local RAG database to answer questions about code or documentation. Use when the user asks about code, functions, symbols, API usage, or technical documentation from the indexed codebase.
---

Search the local RAG database iteratively to answer a question about code or documentation.

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
