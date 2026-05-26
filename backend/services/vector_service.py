import os
import hashlib
import logging
from typing import List, Dict, Any, Optional, Callable
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from services.llm_factory import get_embeddings
from tools.mock_data import MOCK_GITHUB_REPOS, MOCK_CONFLUENCE_PAGES

PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "chroma")

# Ensure directory exists
os.makedirs(PERSIST_DIR, exist_ok=True)

# Set up logging for Vector Store operations
logger = logging.getLogger("aegis_backend.vector_service")

class VectorService:
    def __init__(self):
        logger.info("Initializing Chroma VectorStore service databases...")
        self.embeddings = get_embeddings()
        
        self.confluence_db = Chroma(
            collection_name="confluence_pages",
            embedding_function=self.embeddings,
            persist_directory=PERSIST_DIR
        )
        self.github_db = Chroma(
            collection_name="github_code",
            embedding_function=self.embeddings,
            persist_directory=PERSIST_DIR
        )
        logger.info(f"Chroma DB connections established in persistent folder: {PERSIST_DIR}")

    def _compute_hash(self, content: str) -> str:
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _get_code_language(self, file_path: str) -> Optional[Language]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".py":
            return Language.PYTHON
        elif ext in [".js", ".jsx"]:
            return Language.JS
        elif ext in [".ts", ".tsx"]:
            return Language.TS
        elif ext == ".html":
            return Language.HTML
        elif ext == ".go":
            return Language.GO
        elif ext == ".java":
            return Language.JAVA
        elif ext == ".cpp" or ext == ".h":
            return Language.CPP
        return None

    def sync_confluence_pages(self, pages: List[Dict[str, Any]], callback: Optional[Callable[[str], None]] = None):
        """
        Incrementally index Confluence pages.
        If a page hash matches existing metadata, skip. Otherwise, delete and re-index.
        """
        logger.info(f"Starting Confluence VectorStore sync for {len(pages)} pages.")
        for page in pages:
            page_id = page["id"]
            title = page["title"]
            body = page["body"]
            parent_id = page.get("parent_id")
            last_updated = page.get("last_updated", "")
            
            content_hash = self._compute_hash(body)
            
            msg = f"Checking Confluence page '{title}' ({page_id})..."
            logger.info(msg)
            if callback:
                callback(msg)
                
            # Check if page exists with same hash
            existing = self.confluence_db.get(where={"page_id": page_id})
            if existing and existing["ids"]:
                # Grab metadata of the first chunk
                first_meta = existing["metadatas"][0]
                if first_meta.get("hash") == content_hash:
                    msg = f"-> Confluence page '{title}' is up to date (hash matches). Skipping."
                    logger.info(msg)
                    if callback:
                        callback(msg)
                    continue
                
                # If hash differs, delete old chunks
                msg = f"-> Page content updated. Purging old chunks for '{title}'..."
                logger.info(msg)
                if callback:
                    callback(msg)
                self.confluence_db.delete(ids=existing["ids"])
            
            # Smart chunking for Confluence: Recursive Text Splitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=150,
                separators=["\n\n", "\n", " ", ""]
            )
            
            chunks = splitter.split_text(body)
            docs = []
            for i, chunk in enumerate(chunks):
                doc = Document(
                    page_content=f"Page Title: {title}\nContent:\n{chunk}",
                    metadata={
                        "page_id": page_id,
                        "title": title,
                        "parent_id": parent_id or "none",
                        "last_updated": last_updated,
                        "hash": content_hash,
                        "chunk_index": i,
                        "source": "confluence"
                    }
                )
                docs.append(doc)
            
            if docs:
                self.confluence_db.add_documents(docs)
                msg = f"-> Indexed '{title}' in {len(docs)} chunks."
                logger.info(msg)
                if callback:
                    callback(msg)
                    
        logger.info("Confluence VectorStore sync completed.")

    def sync_github_organization(self, org_name: str, callback: Optional[Callable[[str], None]] = None):
        """
        Incrementally index all repos in a GitHub Organization.
        Iterate through files, check hash, and index code with syntax splitters.
        """
        logger.info(f"Starting GitHub VectorStore sync for organization: '{org_name}'")
        github_token = os.getenv("GITHUB_TOKEN")
        
        if github_token and org_name != "mock-org":
            # Real GitHub API syncing
            import requests
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {github_token}"
            }
            
            msg = f"Fetching repository list for organization '{org_name}'..."
            logger.info(msg)
            if callback:
                callback(msg)
                
            repos_url = f"https://api.github.com/orgs/{org_name}/repos"
            try:
                res = requests.get(repos_url, headers=headers)
                if res.status_code != 200:
                    msg = f"Failed to fetch repositories (Status: {res.status_code}). Aborting."
                    logger.error(msg)
                    if callback:
                        callback(msg)
                    return
                repos = res.json()
            except Exception as e:
                msg = f"Error fetching repos: {str(e)}"
                logger.error(msg, exc_info=True)
                if callback:
                    callback(msg)
                return
                
            for repo in repos:
                repo_name = repo["name"]
                msg = f"Processing repository '{repo_name}'..."
                logger.info(msg)
                if callback:
                    callback(msg)
                
                # Fetch repo file tree recursively
                tree_url = f"https://api.github.com/repos/{org_name}/{repo_name}/git/trees/{repo['default_branch']}?recursive=1"
                try:
                    tree_res = requests.get(tree_url, headers=headers)
                    if tree_res.status_code != 200:
                        msg = f"-> Failed to fetch file tree for '{repo_name}'. Skipping."
                        logger.warning(msg)
                        if callback:
                            callback(msg)
                        continue
                    tree_data = tree_res.json()
                    files = [node for node in tree_data.get("tree", []) if node["type"] == "blob"]
                except Exception as e:
                    msg = f"-> Error fetching tree: {str(e)}"
                    logger.error(msg, exc_info=True)
                    if callback:
                        callback(msg)
                    continue
                    
                for file_node in files:
                    file_path = file_node["path"]
                    # Skip binary or unwanted extensions
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in [".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".pyc", ".db"]:
                        continue
                        
                    file_sha = file_node["sha"]
                    
                    # Check if file already indexed and unchanged
                    existing = self.github_db.get(where={"$and": [{"repo_name": {"$eq": repo_name}}, {"file_path": {"$eq": file_path}}]})
                    if existing and existing["ids"]:
                        first_meta = existing["metadatas"][0]
                        if first_meta.get("hash") == file_sha:
                            continue
                        # If changed, delete
                        logger.info(f"File '{file_path}' in repo '{repo_name}' updated. Purging old chunks.")
                        self.github_db.delete(ids=existing["ids"])
                        
                    # Fetch file content
                    raw_url = f"https://api.github.com/repos/{org_name}/{repo_name}/contents/{file_path}"
                    try:
                        content_res = requests.get(raw_url, headers=headers)
                        if content_res.status_code == 200:
                            import base64
                            content_data = content_res.json()
                            content = base64.b64decode(content_data["content"]).decode("utf-8", errors="ignore")
                            self._index_single_file(repo_name, file_path, content, file_sha, callback)
                    except Exception as e:
                        msg = f"--> Error indexing file {file_path}: {e}"
                        logger.error(msg, exc_info=True)
                        if callback:
                            callback(msg)
        else:
            # Fallback to Mock Organization database sync
            msg = f"Using Mock GitHub Organization '{org_name}'..."
            logger.info(msg)
            if callback:
                callback(msg)
                
            for repo_name, repo in MOCK_GITHUB_REPOS.items():
                msg = f"Processing repository '{repo_name}'..."
                logger.info(msg)
                if callback:
                    callback(msg)
                    
                for file_path, content in repo["files"].items():
                    file_sha = self._compute_hash(content)
                    
                    # Check if file already indexed and unchanged
                    existing = self.github_db.get(where={"file_path": file_path})
                    matches_existing = False
                    if existing and existing["ids"]:
                        for idx, meta in enumerate(existing["metadatas"]):
                            if meta.get("repo_name") == repo_name and meta.get("hash") == file_sha:
                                matches_existing = True
                                break
                                
                        if matches_existing:
                            msg = f"-> File '{file_path}' in repo '{repo_name}' is up to date. Skipping."
                            logger.info(msg)
                            if callback:
                                callback(msg)
                            continue
                            
                        # If hash differs, delete specific chunks
                        matching_ids = [existing["ids"][idx] for idx, meta in enumerate(existing["metadatas"]) if meta.get("repo_name") == repo_name]
                        if matching_ids:
                            logger.info(f"Mock file '{file_path}' in '{repo_name}' updated. Purging old chunks.")
                            self.github_db.delete(ids=matching_ids)
                            
                    self._index_single_file(repo_name, file_path, content, file_sha, callback)
                    
        logger.info("GitHub VectorStore sync completed.")

    def _index_single_file(self, repo_name: str, file_path: str, content: str, file_sha: str, callback: Optional[Callable[[str], None]]):
        """Index a single code file into the VectorStore using syntax-aware splitters."""
        lang = self._get_code_language(file_path)
        
        if lang:
            # Use syntax-aware code splitter
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=lang,
                chunk_size=1200,
                chunk_overlap=200
            )
        else:
            # Standard splitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=150
            )
            
        chunks = splitter.split_text(content)
        docs = []
        for i, chunk in enumerate(chunks):
            doc = Document(
                page_content=f"Repository: {repo_name}\nFile: {file_path}\nCode:\n{chunk}",
                metadata={
                    "repo_name": repo_name,
                    "file_path": file_path,
                    "hash": file_sha,
                    "chunk_index": i,
                    "language": lang.value if lang else "text",
                    "source": "github"
                }
            )
            docs.append(doc)
            
        if docs:
            self.github_db.add_documents(docs)
            msg = f"-> Indexed file '{file_path}' in {len(docs)} chunks."
            logger.info(msg)
            if callback:
                callback(msg)

    def search_confluence(self, query: str, limit: int = 5, page_filter: Optional[str] = None) -> List[Document]:
        """Smart retrieval on Confluence database with optional page_id metadata filter."""
        logger.info(f"Searching Confluence vector store. Query: '{query}', limit: {limit}, page_filter: {page_filter}")
        where_filter = {"source": "confluence"}
        if page_filter:
            where_filter = {
                "$and": [
                    {"source": {"$eq": "confluence"}},
                    {"page_id": {"$eq": page_filter}}
                ]
            }
            
        results = self.confluence_db.similarity_search(query, k=limit, where=where_filter)
        logger.info(f"Confluence similarity search retrieved {len(results)} candidate documents.")
        return results

    def search_github(self, query: str, limit: int = 5, repo_filter: Optional[str] = None) -> List[Document]:
        """Smart retrieval on GitHub database with optional repo_name metadata filter."""
        logger.info(f"Searching GitHub vector store. Query: '{query}', limit: {limit}, repo_filter: {repo_filter}")
        where_filter = {"source": "github"}
        if repo_filter:
            where_filter = {
                "$and": [
                    {"source": {"$eq": "github"}},
                    {"repo_name": {"$eq": repo_filter}}
                ]
            }
            
        results = self.github_db.similarity_search(query, k=limit, where=where_filter)
        logger.info(f"GitHub similarity search retrieved {len(results)} candidate code blocks.")
        return results
