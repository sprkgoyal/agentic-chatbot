import os
import requests
from typing import List, Dict, Any, Optional
from langchain.tools import tool
from .mock_data import MOCK_CONFLUENCE_PAGES

CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")

def _get_auth() -> Optional[tuple]:
    if CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN:
        return (CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN)
    return None

def fetch_confluence_page_api(page_id: str) -> Optional[Dict[str, Any]]:
    """Helper to fetch a single page from Confluence API or Mock data."""
    auth = _get_auth()
    if CONFLUENCE_URL and auth:
        # Standard Confluence V1 API endpoint
        url = f"{CONFLUENCE_URL.rstrip('/')}/rest/api/content/{page_id}?expand=body.storage,version,metadata,ancestors"
        try:
            res = requests.get(url, auth=auth, headers={"Accept": "application/json"})
            if res.status_code == 200:
                data = res.json()
                # Extract text body (HTML format from storage)
                body = data.get("body", {}).get("storage", {}).get("value", "")
                
                # Fetch children list
                child_url = f"{CONFLUENCE_URL.rstrip('/')}/rest/api/content/{page_id}/child/page"
                child_res = requests.get(child_url, auth=auth, headers={"Accept": "application/json"})
                children_ids = []
                if child_res.status_code == 200:
                    child_data = child_res.json()
                    children_ids = [c["id"] for c in child_data.get("results", [])]
                
                return {
                    "id": page_id,
                    "title": data.get("title", ""),
                    "body": body,
                    "parent_id": data["ancestors"][-1]["id"] if data.get("ancestors") else None,
                    "last_updated": data.get("version", {}).get("when", ""),
                    "children": children_ids
                }
        except Exception as e:
            print(f"Error fetching page {page_id} from Confluence REST API: {e}")
            return None
    
    # Fallback to Mock Data
    return MOCK_CONFLUENCE_PAGES.get(page_id)

def fetch_confluence_pages_recursive(parent_page_id: str) -> List[Dict[str, Any]]:
    """
    Recursively fetch a parent page and all of its descendants.
    Can be used by the tool or indexer.
    """
    results = []
    to_visit = [parent_page_id]
    visited = set()
    
    while to_visit:
        current_id = to_visit.pop(0)
        if current_id in visited:
            continue
            
        page = fetch_confluence_page_api(current_id)
        if page:
            results.append(page)
            visited.add(current_id)
            # Add child page IDs to the visit queue
            to_visit.extend(page.get("children", []))
            
    return results

@tool
def fetch_confluence_hierarchy(parent_page_id: str) -> str:
    """
    Fetch all documentation pages starting from a parent page ID, recursively
    retrieving all child pages and returning their combined text titles and summaries.
    Useful to discover page content structures.
    """
    pages = fetch_confluence_pages_recursive(parent_page_id)
    if not pages:
        return f"No Confluence pages found starting from parent ID '{parent_page_id}'."
        
    output = [f"Retrieved {len(pages)} pages:"]
    for page in pages:
        parent_info = f" (Parent: {page['parent_id']})" if page['parent_id'] else ""
        body_snippet = page['body'][:200].replace("\n", " ") + "..." if len(page['body']) > 200 else page['body']
        output.append(f"- [{page['id']}] {page['title']}{parent_info}\n  Snippet: {body_snippet}")
        
    return "\n".join(output)
