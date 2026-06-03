import os
import requests
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from langchain.tools import tool
from .mock_data import MOCK_CONFLUENCE_PAGES

logger = logging.getLogger("aegis_backend.confluence_tools")

CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")

def _get_auth() -> Optional[tuple]:
    if CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN:
        return (CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN)
    return None

def fetch_confluence_page_api(page_id: str) -> Optional[Dict[str, Any]]:
    """Helper to fetch a single page from Confluence API (V2 or V1) or Mock data."""
    auth = _get_auth()
    page_id_str = str(page_id)
    
    if CONFLUENCE_URL and auth:
        base_url = CONFLUENCE_URL.rstrip('/')
        headers = {"Accept": "application/json"}
        
        # Try V2 API first
        v2_url = f"{base_url}/api/v2/pages/{page_id_str}?body-format=storage"
        try:
            logger.info(f"Confluence API: Trying V2 endpoint for page {page_id_str}...")
            res = requests.get(v2_url, auth=auth, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                body = data.get("body", {}).get("storage", {}).get("value", "")
                
                # Fetch children using V2 endpoint
                children_url = f"{base_url}/api/v2/pages/{page_id_str}/children"
                children_ids = []
                try:
                    child_res = requests.get(children_url, auth=auth, headers=headers, timeout=10)
                    if child_res.status_code == 200:
                        child_data = child_res.json()
                        children_ids = [str(c["id"]) for c in child_data.get("results", [])]
                except Exception as e:
                    logger.error(f"Error fetching V2 children for page {page_id_str}: {e}")
                
                return {
                    "id": page_id_str,
                    "title": data.get("title", ""),
                    "body": body,
                    "parent_id": str(data.get("parentId")) if data.get("parentId") else None,
                    "last_updated": data.get("version", {}).get("createdAt", ""),
                    "children": children_ids
                }
            else:
                logger.warning(f"Confluence V2 API returned status {res.status_code} for page {page_id_str}. Trying V1...")
        except Exception as e:
            logger.error(f"Error calling Confluence V2 API for page {page_id_str}: {e}")

        # Fallback to V1 API
        v1_url = f"{base_url}/rest/api/content/{page_id_str}?expand=body.storage,version,metadata,ancestors"
        try:
            logger.info(f"Confluence API: Trying V1 endpoint for page {page_id_str}...")
            res = requests.get(v1_url, auth=auth, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                body = data.get("body", {}).get("storage", {}).get("value", "")
                
                # Fetch children using V1 endpoint
                child_url = f"{base_url}/rest/api/content/{page_id_str}/child/page"
                children_ids = []
                try:
                    child_res = requests.get(child_url, auth=auth, headers=headers, timeout=10)
                    if child_res.status_code == 200:
                        child_data = child_res.json()
                        children_ids = [str(c["id"]) for c in child_data.get("results", [])]
                except Exception as e:
                    logger.error(f"Error fetching V1 children for page {page_id_str}: {e}")
                
                return {
                    "id": page_id_str,
                    "title": data.get("title", ""),
                    "body": body,
                    "parent_id": str(data["ancestors"][-1]["id"]) if data.get("ancestors") else None,
                    "last_updated": data.get("version", {}).get("when", ""),
                    "children": children_ids
                }
            else:
                logger.error(f"Confluence V1 API also failed. Status: {res.status_code}, Response: {res.text}")
        except Exception as e:
            logger.error(f"Error calling Confluence V1 API for page {page_id_str}: {e}")

    # Fallback to Mock Data
    logger.info(f"Falling back to mock Confluence data for page {page_id_str}...")
    mock_page = MOCK_CONFLUENCE_PAGES.get(page_id_str)
    if mock_page:
        # Normalize and ensure types are correct
        return {
            "id": page_id_str,
            "title": mock_page.get("title", ""),
            "body": mock_page.get("body", ""),
            "parent_id": str(mock_page.get("parent_id")) if mock_page.get("parent_id") else None,
            "last_updated": mock_page.get("last_updated", ""),
            "children": [str(cid) for cid in mock_page.get("children", [])]
        }
    return None

def fetch_confluence_pages_recursive(parent_page_id: str) -> List[Dict[str, Any]]:
    """
    Recursively fetch a parent page and all of its descendants.
    Uses breadth-first traversal to discover IDs, and parallel workers to retrieve details.
    """
    parent_id_str = str(parent_page_id)
    visited_ids = set()
    to_visit = [parent_id_str]
    
    auth = _get_auth()
    base_url = CONFLUENCE_URL.rstrip('/') if CONFLUENCE_URL else None
    headers = {"Accept": "application/json"}
    
    # 1. Discover all page IDs in the hierarchy using light BFS (child listings)
    logger.info(f"Discovering Confluence page IDs starting from parent {parent_id_str}...")
    while to_visit:
        current_id = to_visit.pop(0)
        if current_id in visited_ids:
            continue
        visited_ids.add(current_id)
        
        children_ids = []
        if base_url and auth:
            # Try V2 first
            v2_child_url = f"{base_url}/rest/api/v2/pages/{current_id}/children"
            try:
                res = requests.get(v2_child_url, auth=auth, headers=headers, timeout=5)
                if res.status_code == 200:
                    children_ids = [str(c["id"]) for c in res.json().get("results", [])]
                else:
                    # Fallback to V1
                    v1_child_url = f"{base_url}/rest/api/content/{current_id}/child/page"
                    res = requests.get(v1_child_url, auth=auth, headers=headers, timeout=5)
                    if res.status_code == 200:
                        children_ids = [str(c["id"]) for c in res.json().get("results", [])]
            except Exception as e:
                logger.error(f"Error fetching child page list for {current_id}: {e}")
        else:
            # Mock fallback child list
            mock_page = MOCK_CONFLUENCE_PAGES.get(current_id)
            if mock_page:
                children_ids = [str(c) for c in mock_page.get("children", [])]
                
        for cid in children_ids:
            if cid not in visited_ids:
                to_visit.append(cid)
                
    # 2. Fetch full details for all collected IDs in parallel
    results = []
    page_ids_to_fetch = list(visited_ids)
    
    logger.info(f"Fetching full content details for {len(page_ids_to_fetch)} pages in parallel...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        pages = list(executor.map(fetch_confluence_page_api, page_ids_to_fetch))
        for page in pages:
            if page:
                results.append(page)
                
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

