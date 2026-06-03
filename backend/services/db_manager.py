import os
import sqlite3
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db")
DB_FILE = os.path.join(DB_DIR, "chatbot.db")

# Ensure db directory exists
os.makedirs(DB_DIR, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Create Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT, -- Plain text password for simplicity in local dev/testing
        role TEXT NOT NULL, -- 'customer' or 'admin'
        name TEXT NOT NULL,
        userpic TEXT NOT NULL -- identifier of pre-seeded avatar
    );
    """)
    
    # Create Sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    # Create Conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    # Create Messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL, -- 'user' or 'ai'
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_error INTEGER DEFAULT 0,
        status_logs TEXT, -- JSON string of list of status messages
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    );
    """)
    
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()

# --- Users ---

def create_user(username: str, password: Optional[str], role: str, name: str, userpic: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = str(uuid.uuid4())
    try:
        cursor.execute(
            "INSERT INTO users (id, username, password, role, name, userpic) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, password, role, name, userpic)
        )
        conn.commit()
        return {"id": user_id, "username": username, "role": role, "name": name, "userpic": userpic}
    except sqlite3.IntegrityError:
        raise ValueError(f"Username '{username}' already exists.")
    finally:
        conn.close()

def get_user_by_id(user_id: str) -> Optional[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def update_user_profile(user_id: str, name: str, userpic: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET name = ?, userpic = ? WHERE id = ?",
        (name, userpic, user_id)
    )
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def delete_user_account(user_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

# --- Sessions ---

def create_session(user_id: str) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    token = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, created_at)
    )
    conn.commit()
    conn.close()
    return token

def get_user_by_token(token: str) -> Optional[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT u.* FROM users u
        JOIN sessions s ON u.id = s.user_id
        WHERE s.token = ?
        """,
        (token,)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def delete_session(token: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

# --- Conversations ---

def create_conversation(user_id: str, title: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    conv_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO conversations (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, user_id, title, created_at)
    )
    conn.commit()
    conn.close()
    return {"id": conv_id, "user_id": user_id, "title": title, "created_at": created_at}

def get_conversation(conv_id: str) -> Optional[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def list_conversations(user_id: str) -> List[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_conversation(conv_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

# --- Messages ---

def create_message(conv_id: str, role: str, content: str, is_error: bool = False, status_logs: List[str] = None) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    msg_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    status_logs_json = json.dumps(status_logs or [])
    cursor.execute(
        """
        INSERT INTO messages (id, conversation_id, role, content, created_at, is_error, status_logs)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (msg_id, conv_id, role, content, created_at, 1 if is_error else 0, status_logs_json)
    )
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "created_at": created_at,
        "is_error": is_error,
        "status_logs": status_logs or []
    }

def list_messages(conv_id: str) -> List[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", (conv_id,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        d["is_error"] = bool(d["is_error"])
        try:
            d["status_logs"] = json.loads(d["status_logs"]) if d.get("status_logs") else []
        except Exception:
            d["status_logs"] = []
        results.append(d)
    return results
