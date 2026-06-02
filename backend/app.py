import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import run_agent_stream, vector_service
from tools.confluence_tools import fetch_confluence_pages_recursive

# Configure standard python logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("aegis_backend")

app = FastAPI(title="Agentic Chatbot Backend")

# Enable CORS for the frontend React application
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

class ConfluenceSyncRequest(BaseModel):
    parent_page_id: str

class GitHubSyncRequest(BaseModel):
    org_name: str

METADATA_FILE = os.path.join(os.path.dirname(__file__), "db", "metadata.json")

def get_metadata() -> dict:
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_confluence_sync": "Never", "last_github_sync": "Never"}

def update_metadata(key: str, value: str):
    data = get_metadata()
    data[key] = value
    try:
        os.makedirs(os.path.dirname(METADATA_FILE), exist_ok=True)
        with open(METADATA_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to write metadata to file: {e}")

@app.on_event("startup")
def startup_event():
    logger.info("Initializing AEGIS Chatbot Backend...")
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    if openai_key:
        logger.info("Active Provider: OpenAI (found OPENAI_API_KEY)")
    if google_key:
        logger.info("Active Provider: Google Gemini (found GOOGLE_API_KEY/GEMINI_API_KEY)")
    if not openai_key and not google_key:
        logger.warning("No LLM API keys found! System will require configurations prior to running queries.")

@app.get("/api/health")
def health():
    """Verify backend, API configurations, and last sync times."""
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    meta = get_metadata()
    
    return {
        "status": "healthy",
        "has_openai_key": bool(openai_key),
        "has_google_key": bool(google_key),
        "active_provider": "openai" if openai_key else ("google" if google_key else "none"),
        "confluence_parent_page_id": os.getenv("CONFLUENCE_PARENT_PAGE_ID", "100"),
        "github_org": os.getenv("GITHUB_ORG", "mock-org"),
        "last_confluence_sync": meta.get("last_confluence_sync", "Never"),
        "last_github_sync": meta.get("last_github_sync", "Never")
    }

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    POST endpoint that runs the agent asynchronously and yields Server-Sent Events (SSE).
    """
    query_snippet = request.message[:60] + "..." if len(request.message) > 60 else request.message
    logger.info(f"POST /api/chat - Query: '{query_snippet}'")

    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not openai_key and not google_key:
        logger.error("POST /api/chat failed - Missing API keys credentials.")
        raise HTTPException(
            status_code=400,
            detail="Missing API Keys! Please configure OPENAI_API_KEY or GOOGLE_API_KEY / GEMINI_API_KEY."
        )

    queue = asyncio.Queue()

    def status_cb(msg: str):
        logger.info(f"[Agent Status] {msg}")
        queue.put_nowait({"type": "status", "message": msg})

    async def run_agent():
        logger.info("Starting agent async execution...")
        try:
            async for chunk in run_agent_stream(request.message, status_cb):
                await queue.put({"type": "content", "content": chunk})
            logger.info("Agent async execution completed successfully.")
        except Exception as e:
            logger.error(f"Error during agent async execution: {str(e)}", exc_info=True)
            await queue.put({"type": "error", "message": str(e)})
        finally:
            logger.info("Terminating SSE client stream.")
            await queue.put({"type": "done"})

    # Run the agent in the background task loop
    asyncio.create_task(run_agent())

    async def event_generator():
        while True:
            item = await queue.get()
            if item["type"] == "done":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            elif item["type"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': item['message']})}\n\n"
                break
            else:
                yield f"data: {json.dumps(item)}\n\n"
            queue.task_done()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/sync/confluence")
async def sync_confluence_endpoint(request: ConfluenceSyncRequest):
    """
    Streams Confluence synchronization progress logs in real-time.
    """
    logger.info(f"POST /api/sync/confluence - Parent Page ID: '{request.parent_page_id}'")
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def log_cb(msg: str):
        logger.info(f"[Confluence Sync] {msg}")
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    def run_sync():
        try:
            log_cb(f"🚀 Initializing Confluence Sync recursively for Page ID '{request.parent_page_id}'...")
            pages = fetch_confluence_pages_recursive(request.parent_page_id)
            log_cb(f"Fetched {len(pages)} pages. Starting indexing...")
            vector_service.sync_confluence_pages(pages, log_cb)
            update_metadata("last_confluence_sync", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            log_cb("✅ Confluence indexing finished successfully!")
        except Exception as e:
            logger.error(f"Error during Confluence sync run: {str(e)}", exc_info=True)
            log_cb(f"❌ Error during Confluence sync: {str(e)}")
        finally:
            logger.info("Confluence sync stream finalized.")
            loop.call_soon_threadsafe(queue.put_nowait, "DONE")

    loop.run_in_executor(None, run_sync)

    async def event_generator():
        while True:
            msg = await queue.get()
            if msg == "DONE":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            yield f"data: {json.dumps({'type': 'log', 'message': msg})}\n\n"
            queue.task_done()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/sync/github")
async def sync_github_endpoint(request: GitHubSyncRequest):
    """
    Streams GitHub repository synchronization logs in real-time.
    """
    logger.info(f"POST /api/sync/github - Organization: '{request.org_name}'")
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def log_cb(msg: str):
        logger.info(f"[GitHub Sync] {msg}")
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    def run_sync():
        try:
            log_cb(f"🚀 Initializing GitHub Sync for Organization '{request.org_name}'...")
            vector_service.sync_github_organization(request.org_name, log_cb)
            update_metadata("last_github_sync", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            log_cb("✅ GitHub codebase indexing finished successfully!")
        except Exception as e:
            logger.error(f"Error during GitHub sync run: {str(e)}", exc_info=True)
            log_cb(f"❌ Error during GitHub sync: {str(e)}")
        finally:
            logger.info("GitHub sync stream finalized.")
            loop.call_soon_threadsafe(queue.put_nowait, "DONE")

    loop.run_in_executor(None, run_sync)

    async def event_generator():
        while True:
            msg = await queue.get()
            if msg == "DONE":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            yield f"data: {json.dumps({'type': 'log', 'message': msg})}\n\n"
            queue.task_done()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
