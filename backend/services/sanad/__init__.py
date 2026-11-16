"""Sanad AI: the built-in agent behind the standalone Sanad chat.

    dataset   the Sanad tables, loaded into a read-only SQLite database
    corpus    the document collections, with page-level BM25 retrieval
    tools     what the agent can do: run_sql, search_documents, render_chart
    agent     the Claude tool loop (streaming), one run per question
    direct    standard reports from the same tools, for when no model is connected
    engine    sessions, queries and traces behind the /api/ram contract
"""
