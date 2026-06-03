import os
import hashlib
import logging
from typing import List, Dict, Any, Optional, Callable
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from services.llm_factory import get_embeddings
from tools.mock_data import MOCK_GITHUB_REPOS

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
        self.github_repos_metadata_db = Chroma(
            collection_name="github_repos_metadata",
            embedding_function=self.embeddings,
            persist_directory=PERSIST_DIR
        )
        logger.info(f"Chroma DB connections established in persistent folder: {PERSIST_DIR}")

    def _compute_hash(self, content: str) -> str:
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def sync_confluence_pages(self, pages: List[Dict[str, Any]], callback: Optional[Callable[[str], None]] = None):
        """
        Incrementally index Confluence pages in bulk.
        If a page hash matches existing metadata, skip. Otherwise, delete and re-index.
        """
        logger.info(f"Starting Confluence VectorStore sync for {len(pages)} pages.")
        
        all_docs_to_add = []
        ids_to_delete = []
        
        for page in pages:
            page_id = str(page["id"])
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
                
                # If hash differs, queue old chunks for deletion
                msg = f"-> Page content updated. Queueing old chunks deletion for '{title}'..."
                logger.info(msg)
                if callback:
                    callback(msg)
                ids_to_delete.extend(existing["ids"])
            
            # Smart chunking for Confluence: Recursive Text Splitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=150,
                separators=["\n\n", "\n", " ", ""]
            )
            
            chunks = splitter.split_text(body)
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
                all_docs_to_add.append(doc)
                
            msg = f"-> Prepared '{title}' in {len(chunks)} chunks."
            logger.info(msg)
            if callback:
                callback(msg)
                
        # Bulk Database Writes
        if ids_to_delete:
            msg = f"Deleting {len(ids_to_delete)} outdated Confluence chunks..."
            logger.info(msg)
            if callback:
                callback(msg)
            self.confluence_db.delete(ids=ids_to_delete)
            
        if all_docs_to_add:
            msg = f"Adding {len(all_docs_to_add)} chunks to Confluence DB..."
            logger.info(msg)
            if callback:
                callback(msg)
            self.confluence_db.add_documents(all_docs_to_add)
            
        logger.info("Confluence VectorStore sync completed.")

    def sync_github_organization(self, org_name: str, callback: Optional[Callable[[str], None]] = None):
        """
        Incrementally index metadata about all repos in a GitHub Organization.
        Uses vectorstore to store metadata about github repos.
        """
        logger.info(f"Starting GitHub Repository metadata sync for organization: '{org_name}'")
        github_token = os.getenv("GITHUB_TOKEN")
        
        repos = []
        
        if github_token and org_name != "mock-org" and github_token != "your_github_personal_access_token_here":
            # Real GitHub API syncing for repository list
            import requests
            from tools.github_tools import get_github_api_base
            api_base = get_github_api_base()
            
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {github_token}"
            }
            
            msg = f"Fetching repository list for organization '{org_name}' from {api_base}..."
            logger.info(msg)
            if callback:
                callback(msg)
                
            repos_url = f"{api_base}/orgs/{org_name}/repos?per_page=100"
            try:
                res = requests.get(repos_url, headers=headers, timeout=15)
                if res.status_code != 200:
                    # Fallback to user repos if org repos fails or if it's a user rather than org
                    user_repos_url = f"{api_base}/users/{org_name}/repos?per_page=100"
                    logger.warning(f"Org repos fetch failed. Trying user repos: {user_repos_url}...")
                    res = requests.get(user_repos_url, headers=headers, timeout=15)
                    
                if res.status_code == 200:
                    repos = res.json()
                else:
                    msg = f"Failed to fetch repositories (Status: {res.status_code}). Response: {res.text}. Aborting."
                    logger.error(msg)
                    if callback:
                        callback(msg)
                    return
            except Exception as e:
                msg = f"Error fetching repos: {str(e)}"
                logger.error(msg, exc_info=True)
                if callback:
                    callback(msg)
                return
        else:
            # Fallback to Mock Organization database sync
            msg = f"Using Mock GitHub Organization '{org_name}'..."
            logger.info(msg)
            if callback:
                callback(msg)
                
            repos = [
                {
                    "name": name,
                    "description": data.get("description", "No description"),
                    "language": data.get("language", "Python"),
                    "topics": data.get("topics", []),
                    "default_branch": "main"
                } for name, data in MOCK_GITHUB_REPOS.items()
            ]
            
        docs_to_add = []
        ids_to_delete = []
        
        for repo in repos:
            repo_name = repo["name"]
            desc = repo.get("description") or "No description"
            lang = repo.get("language") or "Unknown"
            topics = repo.get("topics") or []
            branch = repo.get("default_branch") or "main"
            
            topics_str = ", ".join(topics) if isinstance(topics, list) else str(topics)
            
            # Format repository metadata text representation for vector search
            content = (
                f"Repository Name: {repo_name}\n"
                f"Description: {desc}\n"
                f"Primary Language: {lang}\n"
                f"Topics: {topics_str}\n"
                f"Default Branch: {branch}"
            )
            
            content_hash = self._compute_hash(content)
            
            msg = f"Checking repository metadata for '{repo_name}'..."
            logger.info(msg)
            if callback:
                callback(msg)
            
            # Check if exists with same hash
            existing = self.github_repos_metadata_db.get(where={"repo_name": repo_name})
            if existing and existing["ids"]:
                first_meta = existing["metadatas"][0]
                if first_meta.get("hash") == content_hash:
                    msg = f"-> Repository metadata for '{repo_name}' is up to date. Skipping."
                    logger.info(msg)
                    if callback:
                        callback(msg)
                    continue
                ids_to_delete.extend(existing["ids"])
            
            doc = Document(
                page_content=content,
                metadata={
                    "repo_name": repo_name,
                    "hash": content_hash,
                    "source": "github_metadata"
                }
            )
            docs_to_add.append(doc)
            msg = f"-> Prepared metadata for repo '{repo_name}'."
            logger.info(msg)
            if callback:
                callback(msg)
                
        if ids_to_delete:
            self.github_repos_metadata_db.delete(ids=ids_to_delete)
        if docs_to_add:
            self.github_repos_metadata_db.add_documents(docs_to_add)
            msg = f"✅ Indexed metadata for {len(docs_to_add)} repositories."
            logger.info(msg)
            if callback:
                callback(msg)
                
        logger.info("GitHub VectorStore sync completed.")

    def search_confluence(self, query: str, limit: int = 5, page_filter: Optional[str] = None) -> List[Document]:
        """Smart retrieval on Confluence database with optional page_id metadata filter."""
        logger.info(f"Searching Confluence vector store. Query: '{query}', limit: {limit}, page_filter: {page_filter}")
        where_filter = {"source": "confluence"}
        if page_filter:
            where_filter = {
                "source": "confluence",
                "page_id": page_filter
            }
            
        results = self.confluence_db.similarity_search(query, k=limit, filter=where_filter)
        logger.info(f"Confluence similarity search retrieved {len(results)} candidate documents.")
        return results

    def search_github(self, query: str, limit: int = 5, repo_filter: Optional[str] = None) -> List[Document]:
        """Smart retrieval on GitHub metadata database with optional repo_name metadata filter."""
        logger.info(f"Searching GitHub metadata vector store. Query: '{query}', limit: {limit}, repo_filter: {repo_filter}")
        where_filter = {"source": "github_metadata"}
        if repo_filter:
            where_filter = {
                "source": "github_metadata",
                "repo_name": repo_filter
            }
            
        results = self.github_repos_metadata_db.similarity_search(query, k=limit, filter=where_filter)
        logger.info(f"GitHub similarity search retrieved {len(results)} candidate metadata documents.")
        return results
