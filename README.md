# AEGIS Agentic Chatbot Portal

AEGIS is a state-of-the-art internal developer-focused chatbot system. It integrates codebases (GitHub), documents (Confluence), and issue tracking (Jira) to provide rich, unified answers to systems and software queries.

---

## 🌟 Key Features

1. **Stateful Agent Loop**: Built on top of LangGraph and the `deepagents` harness for multi-step reasoning, planning, and tool execution.
2. **Real-time SSE Telemetry**: Streams both background actions (like tool execution and document relevance grading) and final chat tokens to the frontend UI using Server-Sent Events (SSE).
3. **Smart Vector Stores with Incremental Updates**:
   - **Chroma** persistent databases local to the server.
   - **Smart Chunking**: Syntax-aware splitters (`from_language`) preserve structural boundaries of files (Python, JS, TS, HTML), while recursive headers splitters parse Confluence articles.
   - **Incremental Sync**: Uses MD5 hashes of pages and file commits to skip unmodified elements, updating only newly created or modified files.
4. **LLM Document Grader**: Dynamically evaluates the relevance of fetched chunks using a structured LLM call and drops irrelevant fragments from the context before generating response text.
5. **Hybrid Integration**: Automatically connects to real APIs (GitHub REST, Confluence Cloud, Jira Cloud) if environment tokens are configured; otherwise, it seamlessly falls back to an expressive local mock microservices database.
6. **Premium Glowy UI**: A sleek, cyber-themed, glassmorphic layout written in React (Vite) and vanilla CSS, featuring typing cursor status feeds and copyable terminal code block containers.

---

## 📂 Project Structure

```text
agentic-chatbot/
├── backend/
│   ├── app.py                      # FastAPI server & SSE endpoints
│   ├── agent.py                    # LangGraph/deepagents setup & vector search tools
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Configuration template
│   ├── services/
│   │   ├── llm_factory.py          # Dynamic LLM provider (OpenAI vs Gemini) loader
│   │   ├── vector_service.py       # Chroma collections, splitters & incremental indexing
│   │   └── document_grader.py      # Structured-output relevance evaluator
│   └── tools/
│       ├── mock_data.py            # Simulated developer ecosystem data
│       ├── github_tools.py         # Repo code & PR interaction wrapper
│       ├── confluence_tools.py     # Hierarchical page traverse wrapper
│       └── jira_tools.py           # Epics/Stories/Tasks fetching wrapper
└── frontend/
    ├── index.html                  # Core HTML template
    ├── package.json                # Frontend Node dependencies
    ├── src/
    │   ├── main.jsx                # React Entrypoint
    │   ├── App.jsx                 # Cockpit interface, layout & chat loop
    │   ├── index.css               # Neon-glow glassmorphic styles
    │   └── components/
    │       └── SyncPanel.jsx       # Vector store sync controller & logs console
```

---

## 🚀 Setup & Launch

### 1. Credentials Setup
Copy the `.env.example` in `backend/` to `.env` and fill in:
- `GOOGLE_API_KEY` (Gemini Flash/Pro) or `OPENAI_API_KEY` (GPT-4o/Mini)
- *(Optional)* GitHub, Confluence, and Jira credentials for live data integration.

### 2. Launch Backend
```bash
cd backend
python -m venv .venv
# Activate:
#   Windows (PowerShell): .venv\Scripts\Activate.ps1
#   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
The API server will launch at `http://localhost:8000`.

### 3. Launch Frontend
```bash
cd frontend
npm install
npm run dev
```
Open your browser and navigate to `http://localhost:5173`.
