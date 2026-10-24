# CorelDRAW MCP Client Configuration Guide

> Zero API Key Cost! Connect your local CorelDRAW MCP server directly to your existing AI Subscription Apps (Claude Desktop, Cursor, OpenCode, ChatGPT).

---

## Mode 1: Claude Desktop (Recommended for Claude Pro Users)

Claude Desktop connects to local tools via `stdio` (Standard I/O). **No URL, no HTTP/HTTPS, and no API key required!**

### Step 1: Open Configuration File
1. Press `Win + R` on Windows, type `%APPDATA%\Claude` and hit Enter.
2. Locate or create the file `claude_desktop_config.json`.

### Step 2: Paste the Configuration
Paste the following JSON configuration into `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "coreldraw-live": {
      "command": "python",
      "args": [
        "C:\\path\\to\\coreldraw-live-mcp\\server\\server.py",
        "--transport",
        "stdio"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```
*(If using a virtual environment, replace `"python"` with `"C:\\path\\to\\coreldraw-live-mcp\\.venv\\Scripts\\python.exe"`.)*

### Step 3: Restart Claude Desktop
1. Close and re-open Claude Desktop.
2. Click the 🔨 (hammer) connector icon in the chat bar. You will see **75+ CorelDRAW tools** loaded!
3. Ask Claude Desktop in natural language:
   > *"Open room_template.cdr, change room number to 301, department to R&D Center, and export PDF & DXF files."*

---

## Mode 2: Network / Web Connector Mode (HTTP / HTTPS / SSE)

If an app (or web connector) explicitly demands a `http://` or `https://` URL:

### Option A: Standard HTTP / SSE Mode
Start the HTTP server on port 8765:
```bash
cd server
python server.py --transport streamable-http --port 8765
```
URLs exposed:
- **HTTP MCP Endpoint**: `http://127.0.0.1:8765/mcp`
- **SSE Endpoint**: `http://127.0.0.1:8765/sse`

### Option B: HTTPS Mode (Self-Signed SSL)
If an external tool requires `https://`:
```bash
cd server
python server_https.py --port 8765
```
URLs exposed:
- **HTTPS MCP Endpoint**: `https://127.0.0.1:8765/mcp`
- **HTTPS SSE Endpoint**: `https://127.0.0.1:8765/sse`

---

## Mode 3: Cursor / Windsurf / OpenCode

Cursor and OpenCode automatically discover `.mcp.json` in your workspace root directory.

Simply open this repository in Cursor or OpenCode, open Cursor Settings -> MCP, and enable `coreldraw-live`.

---

## New High-Level Macro Tools Available

Your AI Assistant can now run an entire job in a single tool call!

- `generate_sign_from_template`: Takes template path, placeholder replacements dictionary, auto-fits text overflow, converts curves, and exports PDF, DXF, and preview PNG.
- `batch_generate_signs`: Takes Excel file path and template path to batch-process all room signs into PDF and DXF folders.
- `quick_create_sign`: Creates a custom sign from scratch with specified width/height, text, and colors, and exports production files.
