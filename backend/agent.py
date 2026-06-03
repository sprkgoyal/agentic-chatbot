import os
import json
import logging
from typing import Any, Optional, Callable, AsyncGenerator
from langchain.tools import tool

from services.llm_factory import get_llm
from services.vector_service import VectorService
from services.document_grader import grade_and_filter_documents
from services.mcp_client import MCPClient, create_langchain_tool, get_github_host

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
logger = logging.getLogger("aegis_backend.agent")

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
def query_github_repository_metadata(query: str) -> str:
    """
    Search the GitHub repository metadata vector store for repository names, topics, primary languages, and descriptions.
    Use this to find which repository is relevant for a given feature, task, or question.
    Parameters:
      - query: Semantic search query (e.g. 'authentication service', 'Stripe payment integration')
    """
    emit_status(f"🔍 Searching GitHub Repository Metadata for: '{query}'...")
    
    raw_docs = vector_service.search_github(query, limit=5)
    emit_status(f"💻 Retrieved {len(raw_docs)} repository metadata records.")
    
    if not raw_docs:
        return "No relevant GitHub repository metadata found."
        
    output = []
    for doc in raw_docs:
        repo = doc.metadata.get("repo_name", "Unknown")
        output.append(f"--- GitHub Repository Metadata: '{repo}' ---\n{doc.page_content}\n")
        
    return "\n".join(output)

SYSTEM_PROMPT = """You are a senior microservices and systems engineer chatbot.
Your job is to answer developer queries using the internal knowledge base tools (Jira, Confluence, GitHub).
For each query, choose the most appropriate tool to fetch documentation, code, or tasks.

RULES:
1. Always start by creating or writing a brief TODO list breaking down the steps required to address the user's query. Update your checklist as you proceed.
2. Always start by checking your vector stores using `query_confluence_knowledge_base` or `query_github_repository_metadata` if searching for general concepts, specs, files, functions, or repository names.
3. For live tasks, stories, epics, or pull requests, query `search_jira_issues` or other direct tools.
4. Be extremely concise and professional. Do not add fluff. Focus on service communication, dependency models, and direct answers.
5. If code is requested, show only the exact relevant code blocks or configuration snippets. Do not dump entire files.
6. If a tool execution fails, returns errors, or yields empty/incomplete results, analyze the failure, correct your parameters, and call the tool again with adjusted arguments. You are fully capable of executing tools multiple times in a loop to locate the correct file or document.
7. If the query cannot be answered using the provided tools (e.g. details are completely missing from Confluence, GitHub, and Jira, or the query is entirely out of scope), you MUST explicitly respond stating that you are unable to answer the query (e.g. "I am sorry, but I am unable to answer this query as the required information is not available using the provided tools."). Do not make up answers.
"""

def create_agent():
    """Compiles the agent graph using deepagents harness."""
    llm = get_llm(temperature=0.2)
    
    # Always include static tools
    tools = [
        query_confluence_knowledge_base,
        query_github_repository_metadata,
        fetch_confluence_hierarchy,
        search_jira_issues,
        get_jira_issue_details
    ]
    
    # Check if we should configure the real GitHub MCP client
    github_token = os.getenv("GITHUB_TOKEN")
    github_org = os.getenv("GITHUB_ORG", "mock-org")
    
    mcp_active = False
    if github_token and github_org != "mock-org" and github_token != "your_github_personal_access_token_here":
        try:
            mcp_env = os.environ.copy()
            mcp_env["GITHUB_PERSONAL_ACCESS_TOKEN"] = github_token
            
            github_host = get_github_host()
            if "github.com" not in github_host:
                mcp_env["GITHUB_HOST"] = github_host
                
            emit_status("🔌 Connecting to GitHub MCP server in real-API mode...")
            
            # Start MCP server subprocess
            mcp_cmd = ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-github"]
            mcp_client = MCPClient(mcp_cmd, env=mcp_env)
            mcp_client.start()
            
            # Get list of tools and wrap them as LangChain tools
            mcp_tools = mcp_client.list_tools()
            logger.info(f"Loaded {len(mcp_tools)} tools from GitHub MCP server.")
            
            for m_tool in mcp_tools:
                lc_tool = create_langchain_tool(mcp_client, m_tool)
                tools.append(lc_tool)
                
            mcp_active = True
            emit_status("✅ GitHub MCP server tools registered successfully!")
        except Exception as e:
            logger.error(f"Error starting GitHub MCP client: {e}", exc_info=True)
            emit_status(f"⚠️ Failed to start GitHub MCP client. Falling back to mock GitHub tools: {e}")
            
    if not mcp_active:
        logger.info("Registering mock GitHub tools.")
        tools.extend([
            list_github_repos,
            fetch_github_file,
            list_github_prs,
            get_github_pr_details,
            get_github_pages_info
        ])
        
    emit_status("⚙️ Initializing deepagent harness...")
    from deepagents import create_deep_agent
    agent = create_deep_agent(
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        model=llm
    )
    return agent

async def run_agent_stream(query: str, status_cb: Callable[[str], None]) -> AsyncGenerator[str, None]:
    """
    Runs the agent and streams both status updates and final output.
    Uses status_cb to emit background updates via langchain astream_events.
    """
    set_status_callback(status_cb)
    agent = create_agent()
    
    recursion_limit = int(os.getenv("AGENT_RECURSION_LIMIT", "50"))
    emit_status(f"⚙️ Running agent graph (recursion limit: {recursion_limit})...")
    
    # Use standard astream_events v2
    async for event in agent.astream_events(
        {"messages": [("user", query)]},
        version="v2",
        config={"recursion_limit": recursion_limit}
    ):
        event_type = event["event"]
        name = event["name"]
        
        # Tool start event
        if event_type == "on_tool_start":
            inputs = event["data"].get("input", {})
            emit_status(f"🛠️ Agent invoking tool: `{name}` with inputs: {json.dumps(inputs)}")
        
        # Tool end event
        elif event_type == "on_tool_end":
            emit_status(f"✅ Tool `{name}` finished executing.")
            
        # Chat model stream event (token chunks)
        elif event_type == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk:
                text = _extract_text_content(chunk.content)
                if text:
                    yield text
                    
    set_status_callback(None)

