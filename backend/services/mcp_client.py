import json
import logging
import os
import subprocess
import threading
import time
from typing import Dict, Any, Type, List, Optional
from urllib.parse import urlparse
from pydantic import Field, create_model
from langchain_core.tools import StructuredTool

logger = logging.getLogger("aegis_backend.mcp_client")

class MCPClient:
    def __init__(self, command: List[str], env: Optional[Dict[str, str]] = None):
        self.command = command
        self.env = env if env is not None else os.environ.copy()
        self.process = None
        self.responses = {}
        self.lock = threading.Lock()
        self.reader_thread = None
        self.stderr_thread = None
        self.id_counter = 1
        self.initialized = False

    def start(self):
        logger.info(f"Starting MCP server with command: {self.command}")
        # Start the subprocess with redirected stdin, stdout, stderr
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=self.env
        )
        
        # Start a background thread to read standard output (JSON-RPC responses)
        self.reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader_thread.start()
        
        # Start a background thread to log standard error
        self.stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self.stderr_thread.start()
        
        # Perform the protocol handshake
        self._initialize_server()

    def _read_stdout(self):
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                
                msg = json.loads(line)
                if "id" in msg:
                    msg_id = msg["id"]
                    with self.lock:
                        self.responses[msg_id] = msg
            except Exception as e:
                logger.error(f"Error reading/parsing MCP stdout line: {e}")
                time.sleep(0.1)

    def _read_stderr(self):
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stderr.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    # Log stderr output from the server at a warning level
                    logger.warning(f"[MCP Server Log] {line}")
            except Exception as e:
                logger.error(f"Error reading MCP stderr line: {e}")
                time.sleep(0.1)

    def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("MCP process is not running.")
            
        with self.lock:
            req_id = self.id_counter
            self.id_counter += 1
            
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        
        req_str = json.dumps(req) + "\n"
        try:
            self.process.stdin.write(req_str)
            self.process.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"Failed to write request to MCP process stdin: {e}")
            
        # Poll for response matching the request ID
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self.lock:
                if req_id in self.responses:
                    resp = self.responses.pop(req_id)
                    if "error" in resp:
                        raise RuntimeError(f"MCP server returned error: {resp['error']}")
                    return resp.get("result", {})
            time.sleep(0.02)
            
        raise TimeoutError(f"Timeout waiting for MCP response for method '{method}' (id: {req_id})")

    def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("MCP process is not running.")
            
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        req_str = json.dumps(req) + "\n"
        try:
            self.process.stdin.write(req_str)
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f"Failed to write notification to MCP process stdin: {e}")

    def _initialize_server(self):
        try:
            init_res = self.send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "aegis-chatbot-client",
                    "version": "1.0.0"
                }
            })
            logger.info(f"MCP Server initialized: {init_res.get('serverInfo', 'Unknown')}")
            self.send_notification("notifications/initialized")
            self.initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize MCP Server: {e}")
            self.stop()
            raise

    def stop(self):
        if self.process:
            logger.info("Stopping MCP server process...")
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self.initialized = False

    def list_tools(self) -> List[Dict[str, Any]]:
        if not self.initialized:
            raise RuntimeError("MCP client is not initialized.")
        res = self.send_request("tools/list")
        return res.get("tools", [])

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        if not self.initialized:
            raise RuntimeError("MCP client is not initialized.")
        res = self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        content_list = res.get("content", [])
        text_parts = []
        for content in content_list:
            if content.get("type") == "text":
                text_parts.append(content.get("text", ""))
        return "\n".join(text_parts)

    async def acall_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        # Standard synchronous wrapper since stdin/stdout requires blocking thread access
        # but wraps in async for LangChain compatibility.
        import asyncio
        return await asyncio.to_thread(self.call_tool, tool_name, arguments)


def get_github_host() -> str:
    """Helper to extract host URL or fallback for GitHub Enterprise."""
    enterprise_url = os.getenv("GITHUB_ENTERPRISE_URL")
    if enterprise_url:
        parsed = urlparse(enterprise_url)
        if parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return enterprise_url
    return "https://github.com"


def create_langchain_tool(mcp_client: MCPClient, mcp_tool: Dict[str, Any]) -> StructuredTool:
    """Dynamically converts an MCP tool definition into a LangChain StructuredTool."""
    tool_name = mcp_tool["name"]
    tool_desc = mcp_tool["description"]
    schema = mcp_tool["inputSchema"]
    
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    fields = {}
    for name, prop in properties.items():
        type_str = prop.get("type", "string")
        if type_str == "string":
            t = str
        elif type_str == "integer":
            t = int
        elif type_str == "number":
            t = float
        elif type_str == "boolean":
            t = bool
        elif type_str == "array":
            t = list
        elif type_str == "object":
            t = dict
        else:
            t = Any
            
        is_req = name in required
        desc = prop.get("description", "")
        
        if is_req:
            fields[name] = (t, Field(..., description=desc))
        else:
            fields[name] = (Optional[t], Field(default=None, description=desc))
            
    args_schema = create_model(f"{tool_name}_input", **fields)
    
    def run_tool(**kwargs):
        # Strip out optional None values to match strict schema API expectations
        args = {k: v for k, v in kwargs.items() if v is not None}
        return mcp_client.call_tool(tool_name, args)
        
    async def arun_tool(**kwargs):
        args = {k: v for k, v in kwargs.items() if v is not None}
        return await mcp_client.acall_tool(tool_name, args)
        
    return StructuredTool(
        name=tool_name,
        description=tool_desc,
        args_schema=args_schema,
        func=run_tool,
        coroutine=arun_tool
    )
