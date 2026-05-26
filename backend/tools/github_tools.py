import os
import requests
from typing import List, Dict, Any, Optional
from langchain.tools import tool
from .mock_data import MOCK_GITHUB_REPOS

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ORG = os.getenv("GITHUB_ORG", "mock-org")

def _get_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

@tool
def list_github_repos() -> str:
    """
    List all repositories in the configured GitHub Organization.
    Use this to see what repositories are available to inspect.
    """
    if GITHUB_TOKEN and GITHUB_ORG != "mock-org":
        url = f"https://api.github.com/orgs/{GITHUB_ORG}/repos"
        try:
            res = requests.get(url, headers=_get_headers())
            if res.status_code == 200:
                repos = res.json()
                return "\n".join([f"- {r['name']}: {r.get('description') or 'No description'}" for r in repos])
            return f"Failed to fetch repos from GitHub API (Status: {res.status_code}): {res.text}"
        except Exception as e:
            return f"Error connecting to GitHub: {str(e)}"
    else:
        return "Using Mock Repositories:\n" + "\n".join([
            f"- {name}: {data['description']}" for name, data in MOCK_GITHUB_REPOS.items()
        ])

@tool
def fetch_github_file(repo_name: str, file_path: str, branch: Optional[str] = None) -> str:
    """
    Fetch the content of a specific file from a specific branch in a GitHub repository.
    Parameters:
      - repo_name: Name of the repository
      - file_path: Relative path to the file (e.g. 'main.py' or 'src/utils.js')
      - branch: Branch name (optional, defaults to repository's default branch, e.g., 'main')
    """
    branch_val = branch or "main"
    if GITHUB_TOKEN and GITHUB_ORG != "mock-org":
        # First check repo default branch if branch is not specified
        url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/contents/{file_path}?ref={branch_val}"
        try:
            res = requests.get(url, headers=_get_headers())
            if res.status_code == 200:
                data = res.json()
                if "content" in data:
                    import base64
                    decoded = base64.b64decode(data["content"]).decode("utf-8")
                    return f"Content of {file_path} on branch {branch_val}:\n\n```\n{decoded}\n```"
                return f"Path {file_path} is not a file or has no content."
            return f"Failed to retrieve file (Status: {res.status_code}): {res.text}"
        except Exception as e:
            return f"Error retrieving file: {str(e)}"
    else:
        # Mock database lookup
        repo = MOCK_GITHUB_REPOS.get(repo_name)
        if not repo:
            return f"Repository '{repo_name}' not found."
        
        file_content = repo["files"].get(file_path)
        if file_content is not None:
            return f"Content of {file_path} on branch {branch_val} (MOCK):\n\n```\n{file_content}\n```"
        return f"File '{file_path}' not found in mock repository '{repo_name}'."

@tool
def list_github_prs(repo_name: str, state: Optional[str] = "all") -> str:
    """
    List all pull requests (PRs) in a repository.
    Parameters:
      - repo_name: Name of the repository
      - state: State of PRs ('open', 'closed', 'all')
    """
    if GITHUB_TOKEN and GITHUB_ORG != "mock-org":
        url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/pulls?state={state}"
        try:
            res = requests.get(url, headers=_get_headers())
            if res.status_code == 200:
                prs = res.json()
                output = []
                for pr in prs:
                    output.append(f"PR #{pr['number']}: {pr['title']} [State: {pr['state']}] (Branch: {pr['head']['ref']})")
                return "\n".join(output) if output else "No PRs found."
            return f"Failed to fetch PRs (Status: {res.status_code}): {res.text}"
        except Exception as e:
            return f"Error: {str(e)}"
    else:
        repo = MOCK_GITHUB_REPOS.get(repo_name)
        if not repo:
            return f"Repository '{repo_name}' not found."
        
        output = []
        for pr in repo.get("prs", []):
            if state == "all" or pr["state"] == state:
                output.append(f"PR #{pr['number']}: {pr['title']} [State: {pr['state']}] (Branch: {pr['branch']})")
        return "\n".join(output) if output else "No mock PRs found."

@tool
def get_github_pr_details(repo_name: str, pr_number: int) -> str:
    """
    Retrieve details of a pull request, including comments and reviews.
    Parameters:
      - repo_name: Name of the repository
      - pr_number: PR ID number
    """
    if GITHUB_TOKEN and GITHUB_ORG != "mock-org":
        pr_url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/pulls/{pr_number}"
        comments_url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/pulls/{pr_number}/comments"
        reviews_url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/pulls/{pr_number}/reviews"
        
        try:
            pr_res = requests.get(pr_url, headers=_get_headers())
            if pr_res.status_code != 200:
                return f"Failed to fetch PR #{pr_number} (Status: {pr_res.status_code}): {pr_res.text}"
            
            pr_data = pr_res.json()
            title = pr_data["title"]
            state = pr_data["state"]
            body = pr_data.get("body") or "No description"
            
            # Fetch comments
            comm_res = requests.get(comments_url, headers=_get_headers())
            comments_text = ""
            if comm_res.status_code == 200:
                comments = comm_res.json()
                comments_text = "\n".join([f"- @{c['user']['login']}: {c['body']}" for c in comments])
            
            # Fetch reviews
            rev_res = requests.get(reviews_url, headers=_get_headers())
            reviews_text = ""
            if rev_res.status_code == 200:
                reviews = rev_res.json()
                reviews_text = "\n".join([f"- @{r['user']['login']} ({r['state']}): {r.get('body') or 'No review text'}" for r in reviews])
                
            return (
                f"PR #{pr_number}: {title}\n"
                f"State: {state}\n"
                f"Description: {body}\n\n"
                f"--- Comments ---\n{comments_text or 'No review/file comments.'}\n\n"
                f"--- Reviews ---\n{reviews_text or 'No reviews submitted.'}"
            )
        except Exception as e:
            return f"Error fetching PR details: {str(e)}"
    else:
        # Mock database lookup
        repo = MOCK_GITHUB_REPOS.get(repo_name)
        if not repo:
            return f"Repository '{repo_name}' not found."
        
        pr = next((p for p in repo.get("prs", []) if p["number"] == pr_number), None)
        if not pr:
            return f"PR #{pr_number} not found in mock repository '{repo_name}'."
        
        comments_text = "\n".join([f"- @{c['user']}: {c['body']}" for c in pr.get("comments", [])])
        reviews_text = "\n".join([f"- @{r['user']} ({r['state']}): {r['body']}" for r in pr.get("reviews", [])])
        
        return (
            f"PR #{pr_number}: {pr['title']} (MOCK)\n"
            f"State: {pr['state']}\n"
            f"Branch: {pr['branch']}\n\n"
            f"--- Comments ---\n{comments_text or 'No comments.'}\n\n"
            f"--- Reviews ---\n{reviews_text or 'No reviews.'}"
        )

@tool
def get_github_pages_info(repo_name: str) -> str:
    """
    Get information about the GitHub Pages deployment for a repository.
    """
    if GITHUB_TOKEN and GITHUB_ORG != "mock-org":
        url = f"https://api.github.com/repos/{GITHUB_ORG}/{repo_name}/pages"
        try:
            res = requests.get(url, headers=_get_headers())
            if res.status_code == 200:
                data = res.json()
                return f"GitHub Pages deployment for {repo_name}:\n- URL: {data['html_url']}\n- Status: {data['status']}\n- Source Branch: {data['source']['branch']}"
            return f"No GitHub Pages configured or failed to fetch (Status: {res.status_code})."
        except Exception as e:
            return f"Error: {str(e)}"
    else:
        return f"Mock GitHub Pages Info for '{repo_name}':\n- URL: https://{GITHUB_ORG}.github.io/{repo_name}\n- Status: active\n- Source Branch: gh-pages"
