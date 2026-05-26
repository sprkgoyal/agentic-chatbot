import os
import requests
from typing import List, Dict, Any, Optional
from langchain.tools import tool
from .mock_data import MOCK_JIRA_ISSUES

JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

def _get_auth() -> Optional[tuple]:
    if JIRA_USERNAME and JIRA_API_TOKEN:
        return (JIRA_USERNAME, JIRA_API_TOKEN)
    return None

@tool
def search_jira_issues(jql_query: Optional[str] = None) -> str:
    """
    Search for Jira issues (epics, stories, tasks, bugs) using a JQL query.
    If no JQL is provided, it searches for all issues in the configured project.
    Parameters:
      - jql_query: A valid Jira Query Language string (e.g. 'project = PROJ AND status = "In Progress"')
    """
    auth = _get_auth()
    
    # Determine JQL
    if not jql_query:
        proj = JIRA_PROJECT_KEY or "PROJ"
        jql_query = f"project = {proj} ORDER BY updated DESC"
        
    if JIRA_URL and auth:
        url = f"{JIRA_URL.rstrip('/')}/rest/api/3/search?jql={jql_query}"
        try:
            res = requests.get(url, auth=auth, headers={"Accept": "application/json"})
            if res.status_code == 200:
                data = res.json()
                issues = data.get("issues", [])
                output = []
                for issue in issues:
                    key = issue["key"]
                    fields = issue.get("fields", {})
                    itype = fields.get("issuetype", {}).get("name", "Task")
                    summary = fields.get("summary", "")
                    status = fields.get("status", {}).get("name", "Unknown")
                    output.append(f"[{key}] {itype}: {summary} (Status: {status})")
                return "\n".join(output) if output else "No issues found matching JQL."
            return f"Failed to search Jira (Status: {res.status_code}): {res.text}"
        except Exception as e:
            return f"Error connecting to Jira API: {str(e)}"
    else:
        # Mock database lookup
        # Simulate simple parsing of JQL for "status", "type", or key keywords
        output = []
        query_lower = jql_query.lower()
        
        for issue in MOCK_JIRA_ISSUES:
            # Basic matching for demo purposes
            matched = True
            if "status = " in query_lower:
                for status in ["to do", "in progress", "done"]:
                    if f'status = "{status}"' in query_lower or f"status = '{status}'" in query_lower:
                        if issue["status"].lower() != status:
                            matched = False
            if matched:
                output.append(f"[{issue['key']}] {issue['type']}: {issue['summary']} (Status: {issue['status']})")
                
        return "Using Mock Jira Database:\n" + ("\n".join(output) if output else "No mock issues matched.")

@tool
def get_jira_issue_details(issue_key: str) -> str:
    """
    Get detailed description, status, epic links, and assignee for a specific Jira issue.
    Parameters:
      - issue_key: The issue key (e.g. 'USER-102')
    """
    auth = _get_auth()
    if JIRA_URL and auth:
        url = f"{JIRA_URL.rstrip('/')}/rest/api/3/issue/{issue_key}"
        try:
            res = requests.get(url, auth=auth, headers={"Accept": "application/json"})
            if res.status_code == 200:
                data = res.json()
                fields = data.get("fields", {})
                
                # Parse gRPC fields or custom epic link fields
                summary = fields.get("summary", "")
                status = fields.get("status", {}).get("name", "Unknown")
                description_content = fields.get("description")
                
                # Jira V3 description is a rich text document format (ADF), extract plain text
                description = ""
                if isinstance(description_content, dict):
                    # Simple extraction from ADF JSON
                    text_parts = []
                    for paragraph in description_content.get("content", []):
                        for text_node in paragraph.get("content", []):
                            if text_node.get("type") == "text":
                                text_parts.append(text_node.get("text", ""))
                    description = " ".join(text_parts)
                else:
                    description = str(description_content or "No description")
                
                assignee = fields.get("assignee")
                assignee_name = assignee.get("displayName") if assignee else "Unassigned"
                
                subtasks = fields.get("subtasks", [])
                subtask_keys = [sub["key"] for sub in subtasks]
                
                return (
                    f"Jira Issue: {issue_key}\n"
                    f"Summary: {summary}\n"
                    f"Status: {status}\n"
                    f"Assignee: {assignee_name}\n"
                    f"Description: {description}\n"
                    f"Subtasks: {', '.join(subtask_keys) if subtask_keys else 'None'}"
                )
            return f"Failed to retrieve Jira issue '{issue_key}' (Status: {res.status_code})."
        except Exception as e:
            return f"Error: {str(e)}"
    else:
        # Mock database lookup
        issue = next((i for i in MOCK_JIRA_ISSUES if i["key"].upper() == issue_key.upper()), None)
        if not issue:
            return f"Jira issue '{issue_key}' not found in mock database."
        
        epic_info = f"\nEpic: {issue['epic']}" if issue.get("epic") else ""
        subtasks_info = f"\nSubtasks: {', '.join(issue['subtasks'])}" if issue.get("subtasks") else ""
        
        return (
            f"Jira Issue: {issue['key']} (MOCK)\n"
            f"Type: {issue['type']}\n"
            f"Summary: {issue['summary']}\n"
            f"Status: {issue['status']}\n"
            f"Assignee: {issue['assignee']}\n"
            f"Description: {issue['description']}"
            f"{epic_info}"
            f"{subtasks_info}"
        )
