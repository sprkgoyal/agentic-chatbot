import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel

from agent import run_agent_stream, vector_service
from tools.confluence_tools import fetch_confluence_pages_by_space
from services import db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("aegis_backend")

app = FastAPI(title="Agentic Chatbot Backend")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Models ---

class LoginRequest(BaseModel):
    username: str
    password: Optional[str] = None
    role: Optional[str] = "customer" # Default role for auto-register
    name: Optional[str] = None
    userpic: Optional[str] = "avatar_1"

class UpdateSettingsRequest(BaseModel):
    name: str
    userpic: str

class ChatRequest(BaseModel):
    message: str
    conversation_id: str

class ConversationRequest(BaseModel):
    title: str

class ConfluenceSyncRequest(BaseModel):
    space_id: str

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

# --- Auth Dependencies ---

async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Missing or invalid token")
    token = auth_header.split(" ")[1]
    user = db_manager.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized: Session expired or invalid")
    # Return user dict along with the token
    user["token"] = token
    return user

def get_customer(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "customer":
        raise HTTPException(status_code=403, detail="Forbidden: Customer role required")
    return user

def get_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin role required")
    return user

# --- Auth API ---

@app.post("/api/auth/login")
def login(req: LoginRequest):
    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
        
    user = db_manager.get_user_by_username(username)
    if not user:
        # Auto-register
        role = req.role if req.role in ["customer", "admin"] else "customer"
        name = req.name.strip() if req.name else username
        userpic = req.userpic if req.userpic else "avatar_1"
        try:
            user = db_manager.create_user(username, req.password, role, name, userpic)
            logger.info(f"Auto-registered new user: {username} ({role})")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to register user: {str(e)}")
            
    token = db_manager.create_session(user["id"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "name": user["name"],
            "userpic": user["userpic"]
        }
    }

@app.post("/api/auth/logout")
def logout(user: dict = Depends(get_current_user)):
    db_manager.delete_session(user["token"])
    return {"message": "Logged out successfully"}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "name": user["name"],
        "userpic": user["userpic"]
    }

@app.delete("/api/auth/delete-account")
def delete_account(user: dict = Depends(get_current_user)):
    success = db_manager.delete_user_account(user["id"])
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete account")
    return {"message": "Account deleted successfully"}

# --- User Settings API ---

@app.put("/api/user/settings")
def update_settings(req: UpdateSettingsRequest, user: dict = Depends(get_current_user)):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    success = db_manager.update_user_profile(user["id"], name, req.userpic)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update settings")
    return {"message": "Profile updated successfully"}

# --- Conversations API ---

@app.get("/api/conversations")
def list_chats(user: dict = Depends(get_customer)):
    return db_manager.list_conversations(user["id"])

@app.post("/api/conversations")
def create_chat(req: ConversationRequest, user: dict = Depends(get_customer)):
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    return db_manager.create_conversation(user["id"], title)

@app.delete("/api/conversations/{conv_id}")
def delete_chat(conv_id: str, user: dict = Depends(get_customer)):
    conv = db_manager.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    success = db_manager.delete_conversation(conv_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete conversation")
    return {"message": "Conversation deleted"}

@app.get("/api/conversations/{conv_id}/messages")
def get_messages(conv_id: str, user: dict = Depends(get_customer)):
    conv = db_manager.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return db_manager.list_messages(conv_id)

@app.get("/api/conversations/{conv_id}/download")
def download_chat(conv_id: str, user: dict = Depends(get_customer)):
    conv = db_manager.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    messages = db_manager.list_messages(conv_id)
    
    txt_content = []
    txt_content.append(f"Conversation Title: {conv['title']}")
    txt_content.append(f"Exported Date: {datetime.now().isoformat()}")
    txt_content.append("="*40 + "\n")
    
    for msg in messages:
        sender = "User" if msg["role"] == "user" else "AI Assistant"
        txt_content.append(f"[{msg['created_at']}] {sender}: {msg['content']}")
        txt_content.append("-" * 20)
        
    return PlainTextResponse("\n".join(txt_content), headers={
        "Content-Disposition": f"attachment; filename=chat_{conv_id}.txt"
    })

# --- Chat Stream ---

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, user: dict = Depends(get_customer)):
    """
    POST endpoint that runs the agent and yields Server-Sent Events (SSE).
    Saves conversation history to the SQLite database.
    """
    conv = db_manager.get_conversation(request.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # 1. Save user message to database
    db_manager.create_message(request.conversation_id, "user", request.message)

    # 2. Get conversation history (excluding the current user message since it will be passed explicitly)
    history_messages = db_manager.list_messages(request.conversation_id)[:-1]

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
            async for chunk in run_agent_stream(request.message, status_cb, history_messages):
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
        ai_response_accum = []
        status_logs_accum = []
        is_err = False
        
        while True:
            item = await queue.get()
            if item["type"] == "done":
                # Save AI message to DB when finished
                full_reply = "".join(ai_response_accum)
                if full_reply or is_err:
                    db_manager.create_message(
                        request.conversation_id, 
                        "ai", 
                        full_reply if full_reply else "An error occurred.", 
                        is_error=is_err, 
                        status_logs=status_logs_accum
                    )
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            elif item["type"] == "error":
                is_err = True
                status_logs_accum.append(f"Error: {item['message']}")
                yield f"data: {json.dumps({'type': 'error', 'message': item['message']})}\n\n"
                break
            elif item["type"] == "status":
                status_logs_accum.append(item["message"])
                yield f"data: {json.dumps(item)}\n\n"
            else:
                ai_response_accum.append(item["content"])
                yield f"data: {json.dumps(item)}\n\n"
            queue.task_done()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- Sync API (Admin Only) ---

@app.post("/api/sync/confluence")
async def sync_confluence_endpoint(request: ConfluenceSyncRequest, user: dict = Depends(get_admin)):
    """
    Streams Confluence synchronization progress logs in real-time. Admin only.
    """
    space_id = request.space_id.strip()
    logger.info(f"POST /api/sync/confluence - Space ID: '{space_id}'")
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def log_cb(msg: str):
        logger.info(f"[Confluence Sync] {msg}")
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    def run_sync():
        try:
            log_cb(f"🚀 Initializing Confluence Sync for Space ID '{space_id}' using CQL...")
            pages = fetch_confluence_pages_by_space(space_id)
            log_cb(f"Fetched {len(pages)} pages. Starting indexing...")
            vector_service.sync_confluence_pages(pages, space_id, log_cb)
            update_metadata("last_confluence_sync", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            log_cb("✅ Confluence space indexing finished successfully!")
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

# --- Health Check ---

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
        "last_confluence_sync": meta.get("last_confluence_sync", "Never"),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
