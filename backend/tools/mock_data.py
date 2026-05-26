# Mock data simulating a microservices environment

MOCK_CONFLUENCE_PAGES = {
    "100": {
        "id": "100",
        "title": "Engineering Architecture Hub",
        "body": "Welcome to the Engineering Hub. Our system is built on a distributed microservices architecture. We use an API Gateway, User Service, and Order Service. Services talk to each other via HTTP REST and RabbitMQ event queues. See child pages for detailed service specifications.",
        "parent_id": None,
        "last_updated": "2026-05-10T12:00:00Z",
        "children": ["101", "102"]
    },
    "101": {
        "id": "101",
        "title": "User Service Specifications",
        "body": "User Service handles authentication, profile management, and roles. It is written in Python/FastAPI. Port: 8001. Database: PostgreSQL. User Service publishes 'user.created' events to RabbitMQ when a user registers.",
        "parent_id": "100",
        "last_updated": "2026-05-15T14:30:00Z",
        "children": ["103"]
    },
    "102": {
        "id": "102",
        "title": "Order Service Specifications",
        "body": "Order Service manages cart, checkout, and payments. Written in Node.js/Express. Port: 8002. Database: MongoDB. It listens to 'user.deleted' events to purge carts and calls User Service synchronously via HTTP GET /users/{id} to validate accounts.",
        "parent_id": "100",
        "last_updated": "2026-05-16T09:15:00Z",
        "children": ["104"]
    },
    "103": {
        "id": "103",
        "title": "User Auth & JWT Flow",
        "body": "All incoming HTTP requests from the API Gateway must include an Authorization Bearer token. The token is a JWT signed using HS256 with a secret key. User Service exposes /auth/login and /auth/validate endpoints.",
        "parent_id": "101",
        "last_updated": "2026-05-20T10:00:00Z",
        "children": []
    },
    "104": {
        "id": "104",
        "title": "Payment Gateway Integration",
        "body": "Order Service integrates with Stripe for payment processing. Payment details are sent to Stripe API. On success, Order Service updates the database and emits 'order.placed' event to RabbitMQ for Email Service processing.",
        "parent_id": "102",
        "last_updated": "2026-05-22T16:45:00Z",
        "children": []
    }
}

MOCK_GITHUB_REPOS = {
    "user-service": {
        "name": "user-service",
        "description": "User management microservice",
        "default_branch": "main",
        "files": {
            "main.py": """from fastapi import FastAPI, HTTPException, Depends
import uvicorn
import requests

app = FastAPI(title="User Service")

# Dependency for authorization
def get_current_user(token: str):
    if not token or len(token) < 10:
        raise HTTPException(status_code=401, detail="Invalid auth token")
    return {"id": "usr_99", "role": "admin"}

@app.get("/users/{user_id}")
def read_user(user_id: str, current_user = Depends(get_current_user)):
    return {"id": user_id, "username": f"user_{user_id}", "status": "active"}

@app.post("/auth/login")
def login(payload: dict):
    # Dummy authentication logic
    if payload.get("username") == "admin" and payload.get("password") == "secret":
        return {"access_token": "mock-jwt-token-abcd-1234", "token_type": "bearer"}
    raise HTTPException(status_code=400, detail="Bad credentials")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
""",
            "models.py": """from pydantic import BaseModel

class User(BaseModel):
    id: str
    username: str
    email: str
    role: str = "user"
"""
        },
        "prs": [
            {
                "number": 12,
                "title": "Implement API key authentication",
                "state": "open",
                "branch": "feature/api-key",
                "comments": [
                    {"user": "senior_dev", "body": "Please make sure to encrypt the API keys in the database."},
                    {"user": "pr_author", "body": "Yes, I am using bcrypt to store API key hashes."}
                ],
                "reviews": [
                    {"user": "senior_dev", "state": "CHANGES_REQUESTED", "body": "Need tests for token expiry and database schema updates."}
                ]
            }
        ]
    },
    "order-service": {
        "name": "order-service",
        "description": "Order and payments microservice",
        "default_branch": "main",
        "files": {
            "server.js": """const express = require('express');
const axios = require('axios');
const app = express();
app.use(express.json());

const USER_SERVICE_URL = process.env.USER_SERVICE_URL || 'http://localhost:8001';

app.post('/orders', async (req, res) => {
    const { userId, items, token } = req.body;
    
    try {
        // Validate user against User Service via HTTP
        const userRes = await axios.get(`${USER_SERVICE_URL}/users/${userId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (userRes.status !== 200) {
            return res.status(400).json({ error: 'Invalid user validation' });
        }
        
        const orderId = 'ord_' + Math.random().toString(36).substr(2, 9);
        return res.status(201).json({ orderId, status: 'pending', userId });
    } catch (err) {
        console.error('Failed to validate user:', err.message);
        return res.status(500).json({ error: 'Communication error with User Service', details: err.message });
    }
});

app.listen(8002, () => console.log('Order Service running on port 8002'));
"""
        },
        "prs": [
            {
                "number": 5,
                "title": "Fix user service HTTP timeout issue",
                "state": "closed",
                "branch": "fix/timeout",
                "comments": [
                    {"user": "qa_tester", "body": "Confirmed this solves the gateway timeout issues during load tests."}
                ],
                "reviews": [
                    {"user": "tech_lead", "state": "APPROVED", "body": "Code looks clean, merging this now."}
                ]
            }
        ]
    },
    "api-gateway": {
        "name": "api-gateway",
        "description": "Routing gateway for microservices",
        "default_branch": "main",
        "files": {
            "nginx.conf": """server {
    listen 80;
    
    location /users {
        proxy_pass http://user-service:8001;
    }
    
    location /orders {
        proxy_pass http://order-service:8002;
    }
}
"""
        },
        "prs": []
    }
}

MOCK_JIRA_ISSUES = [
    {
        "key": "ARCH-303",
        "type": "Epic",
        "summary": "Migrate internal service communication to gRPC",
        "status": "In Progress",
        "description": "Currently services talk via HTTP REST APIs. We need to migrate the high-traffic endpoints to gRPC to reduce serialization overhead and leverage HTTP/2 features.",
        "assignee": "Architect Alice",
        "subtasks": ["USER-102", "ORDER-203"]
    },
    {
        "key": "USER-102",
        "type": "Story",
        "summary": "Implement gRPC interface for user profile lookup",
        "status": "In Progress",
        "description": "Expose User validation and retrieval via gRPC service inside user-service. Write proto definition files.",
        "assignee": "Dev Dan",
        "epic": "ARCH-303"
    },
    {
        "key": "ORDER-203",
        "type": "Story",
        "summary": "Integrate gRPC client in Order Service",
        "status": "To Do",
        "description": "Replace HTTP calls to User Service with gRPC client calls using stub files generated from proto definitions.",
        "assignee": "Dev Dave",
        "epic": "ARCH-303"
    },
    {
        "key": "USER-101",
        "type": "Bug",
        "summary": "Fix validation token expiration error",
        "status": "Done",
        "description": "User tokens expired too quickly due to timezone difference in parsing. Modified main.py to check expiry in UTC.",
        "assignee": "Dev Dan",
        "epic": None
    }
]
