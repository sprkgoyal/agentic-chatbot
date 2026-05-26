import os
import sys
from typing import List, Dict, Any, Optional, Callable
from langchain.tools import tool
from langchain_core.messages import SystemMessage, AIMessage, AIMessageChunk

from services.llm_factory import get_llm
from services.vector_service import VectorService
from services.document_grader import grade_and_filter_documents

# Import core tools
from tools.github_tools import (
    list_github_repos,
    fetch_github_file,
    list_github_prs,
    get_github_pr_details,
    get_github_pages_info
)
from tools.confluence_tools import fetch_confluence_hierarchy, fetch_confluence_pages_recursive
from tools.jira_tools import search_jira_issues, get_jira_issue_details

# Initialize global VectorService
vector_service = VectorService()

# Create dynamic status listener hooks
_status_callback: Optional[Callable[[str], None]] = None

def set_status_callback(callback: Optional[Callable[[str], None]]):
    global _status_callback
    _status_callback = callback

def emit_status(message: str):
    if _status_callback:
        _status_callback(message)

def _extract_text_content(content: Any) -> str:
    """
    Safely extracts string text content from a LangChain message content block.
    Gemini or Claude models can return content as a list of dicts (e.g., [{'type': 'text', 'text': '...'}]).
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # Check for standard text block
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(block["text"])
        return "".join(parts)
    elif isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        return content.get("text", str(content))
    return str(content) if content is not None else ""

# Define VectorStore Search Tools with built-in Relevance Grading/Pruning
@tool
def query_confluence_knowledge_base(query: str, page_id: Optional[str] = None) -> str:
    """
    Search the Confluence documentation vector store for system specifications, architecture guides, setup manuals, etc.
    This tool automatically evaluates and prunes irrelevant page chunks using an LLM grader.
    Parameters:
      - query: Semantic search query (e.g., 'gRPC migration plan', 'authentication logic')
      - page_id: Optional parent page ID to filter the search space
    """
    emit_status(f"🔍 Searching Confluence VectorStore for: '{query}'...")
    
    # Retrieve chunks
    raw_docs = vector_service.search_confluence(query, limit=5, page_filter=page_id)
    emit_status(f"📄 Retrieved {len(raw_docs)} candidate chunks from Confluence DB.")
    
    # Grade and filter chunks
    filtered_docs = grade_and_filter_documents(query, raw_docs, emit_status)
    
    if not filtered_docs:
        return "No relevant Confluence documents found for your query after relevance grading."
        
    output = []
    for doc in filtered_docs:
        page_title = doc.metadata.get("title", "Untitled")
        pid = doc.metadata.get("page_id")
        output.append(f"--- Confluence Document: '{page_title}' (ID: {pid}) ---\n{doc.page_content}\n")
        
    return "\n".join(output)

@tool
def query_github_codebase(query: str, repo_name: Optional[str] = None) -> str:
    """
    Search the GitHub repository codebase vector store for code blocks, classes, functions, or config structures.
    This tool automatically evaluates and prunes irrelevant code chunks using an LLM grader.
    Parameters:
      - query: Semantic search query (e.g., 'auth route handling', 'Stripe payment integration')
      - repo_name: Optional repository name to filter the search (e.g., 'user-service')
    """
    emit_status(f"🔍 Searching GitHub Code VectorStore for: '{query}'...")
    
    # Retrieve chunks
    raw_docs = vector_service.search_github(query, limit=6, repo_filter=repo_name)
    emit_status(f"💻 Retrieved {len(raw_docs)} code blocks from GitHub DB.")
    
    # Grade and filter chunks
    filtered_docs = grade_and_filter_documents(query, raw_docs, emit_status)
    
    if not filtered_docs:
        return "No relevant code snippets found for your query after relevance grading."
        
    output = []
    for doc in filtered_docs:
        rname = doc.metadata.get("repo_name")
        fpath = doc.metadata.get("file_path")
        output.append(f"--- GitHub Repository: '{rname}', File: '{fpath}' ---\n{doc.page_content}\n")
        
    return "\n".join(output)

# Combine all tools
ALL_TOOLS = [
    # Vector store search tools
    query_confluence_knowledge_base,
    query_github_codebase,
    
    # Direct live API tools (e.g., for PRs, raw files, lists)
    list_github_repos,
    fetch_github_file,
    list_github_prs,
    get_github_pr_details,
    get_github_pages_info,
    fetch_confluence_hierarchy,
    search_jira_issues,
    get_jira_issue_details
]

SYSTEM_PROMPT = """You are a senior microservices and systems engineer chatbot.
Your job is to answer developer queries using the internal knowledge base tools (Jira, Confluence, GitHub).
For each query, choose the most appropriate tool to fetch documentation, code, or tasks.

RULES:
1. Always start by creating or writing a brief TODO list breaking down the steps required to address the user's query. Update your checklist as you proceed.
2. Always start by checking your vector stores using `query_confluence_knowledge_base` or `query_github_codebase` if searching for general concepts, specs, files, or functions.
3. For live tasks, stories, epics, or pull requests, query `search_jira_issues` or `list_github_prs` directly.
4. Be extremely concise and professional. Do not add fluff. Focus on service communication, dependency models, and direct answers.
5. If code is requested, show only the exact relevant code blocks or configuration snippets. Do not dump entire files.
6. If a tool execution fails, returns errors, or yields empty/incomplete results, analyze the failure, correct your parameters, and call the tool again with adjusted arguments. You are fully capable of executing tools multiple times in a loop to locate the correct file or document.
7. If the query cannot be answered using the provided tools (e.g. details are completely missing from Confluence, GitHub, and Jira, or the query is entirely out of scope), you MUST explicitly respond stating that you are unable to answer the query (e.g. "I am sorry, but I am unable to answer this query as the required information is not available using the provided tools."). Do not make up answers.
"""

def create_agent():
    """Compiles the agent graph using deepagents harness."""
    llm = get_llm(temperature=0.2)
    
    emit_status("⚙️ Initializing deepagent harness...")
    from deepagents import create_deep_agent
    agent = create_deep_agent(
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        model=llm
    )
    return agent

def run_agent_stream(query: str, status_cb: Callable[[str], None]):
    """
    Runs the agent and streams both status updates and final output.
    Uses status_cb to emit background updates.
    """
    set_status_callback(status_cb)
    agent = create_agent()
    
    emit_status("🧠 Planning execution strategy...")
    
    # Load recursion limit from env, defaulting to 50
    recursion_limit = int(os.getenv("AGENT_RECURSION_LIMIT", "50"))
    emit_status(f"⚙️ Running agent graph (recursion limit: {recursion_limit})...")
    
    # Use stream_mode="messages" to yield token chunks in real-time
    response_stream = agent.stream(
        {"messages": [("user", query)]},
        stream_mode="messages",
        config={"recursion_limit": recursion_limit}
    )
    
    for chunk in response_stream:
        # In stream_mode="messages", chunk is a tuple (message, metadata)
        if isinstance(chunk, tuple) and len(chunk) >= 2:
            message, metadata = chunk[0], chunk[1]
            
            # Identify message type via class checking (supports AIMessage and AIMessageChunk)
            if isinstance(message, (AIMessage, AIMessageChunk)):
                # Check for tool call messages and log them
                if hasattr(message, "tool_calls") and message.tool_calls:
                    for tc in message.tool_calls:
                        emit_status(f"🛠️ Agent invoking tool: `{tc['name']}`")
                
                # Yield text deltas
                text = _extract_text_content(message.content)
                if text:
                    yield text
                    
    set_status_callback(None)
