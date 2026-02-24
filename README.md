# Google Tasks MCP Server

An MCP (Model Context Protocol) server that enables AI assistants to manage Google Tasks. Provides five tools for task list management, task creation, listing, completion, and link attachment.

## Tools

| Tool | Description |
|------|-------------|
| `get_lists` | List all Google Tasks task lists |
| `create_task` | Create tasks or subtasks with optional due dates and notes |
| `list_tasks` | List tasks with filtering for completed/hidden items |
| `complete_task` | Toggle task completion status |
| `add_link` | Attach web links (Jira, PRs, repos) to task notes |

## Project Structure

```
gtasks-mcp-server/
├── gtasks_mcp_server/
│   ├── __init__.py
│   ├── __main__.py
│   └── server.py           # MCP server implementation
├── pyproject.toml
├── Makefile
├── README.md
├── .gitignore
├── .env.example
├── credentials.json        # OAuth credentials (gitignored)
└── token.json              # OAuth token (gitignored, auto-generated)
```

## Prerequisites

- Python 3.10+
- A Google Cloud project with the Google Tasks API enabled
- OAuth 2.0 client credentials (Desktop application type)

## Setup

### 1. Google Cloud Configuration

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.
3. Enable the **Google Tasks API**:
   - Navigate to **APIs & Services > Library**.
   - Search for "Tasks API" and click **Enable**.
4. Create OAuth 2.0 credentials:
   - Navigate to **APIs & Services > Credentials**.
   - Click **Create Credentials > OAuth client ID**.
   - Select **Desktop application** as the application type.
   - Download the JSON file and save it as `credentials.json` in the project root.
5. Configure the OAuth consent screen:
   - Navigate to **APIs & Services > OAuth consent screen**.
   - Add your Google account as a test user (required for "External" user type).

### 2. Installation

```bash
git clone https://github.com/your-username/gtasks-mcp-server.git
cd gtasks-mcp-server
make install
```

### 3. First-Time Authentication

Run the auth command to complete the OAuth consent flow:

```bash
make auth

# Or without make:
python3 gtasks_mcp_server/server.py --auth
```

1. A browser window opens for Google sign-in.
2. Grant the requested Google Tasks permissions.
3. The server saves the token to `token.json` in the project root for future use.
4. On success, your task lists are printed to confirm the connection.

Subsequent runs reuse the stored token and automatically refresh it when expired.

## MCP Client Configuration

Replace `/absolute/path/to/gtasks-mcp-server` with the actual path to your clone.

---

### Claude Code

**Using the CLI** (recommended):

```bash
# Project scope (shared with team via .mcp.json)
claude mcp add --transport stdio --scope project gtasks -- \
  python3 \
  /absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py

# User scope (available across all your projects)
claude mcp add --transport stdio --scope user gtasks -- \
  python3 \
  /absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py
```

Verify the server is registered:

```bash
claude mcp list
```

**Manual configuration** -- create or edit `.mcp.json` in your project root (project scope) or `~/.claude.json` (user scope):

```json
{
  "mcpServers": {
    "gtasks": {
      "type": "stdio",
      "command": "python3",
      "args": ["/absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py"]
    }
  }
}
```

Once running, type `/mcp` inside Claude Code to verify the server status and available tools.

---

### Gemini CLI

**Using the CLI**:

```bash
# Project scope (default)
gemini mcp add gtasks \
  python3 \
  /absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py

# User scope (available across all projects)
gemini mcp add -s user gtasks \
  python3 \
  /absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py
```

Verify the server is registered:

```bash
gemini mcp list
```

**Manual configuration** -- create or edit `.gemini/settings.json` in your project root (project scope) or `~/.gemini/settings.json` (user scope):

```json
{
  "mcpServers": {
    "gtasks": {
      "command": "python3",
      "args": ["/absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py"]
    }
  }
}
```

Once running, type `/mcp` inside Gemini CLI to verify the server status and available tools.

---

### Cursor

**Using the UI**: Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`), search for "MCP", and select **View: Open MCP Settings**. This opens the configuration file for editing.

**Manual configuration** -- create or edit `.cursor/mcp.json` in your project root (project scope) or `~/.cursor/mcp.json` (global scope):

```json
{
  "mcpServers": {
    "gtasks": {
      "command": "python3",
      "args": ["/absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py"]
    }
  }
}
```

After saving, restart Cursor or reload MCP servers from the Command Palette.

---

### Claude Desktop

Edit the Claude Desktop configuration file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gtasks": {
      "command": "python3",
      "args": ["/absolute/path/to/gtasks-mcp-server/gtasks_mcp_server/server.py"]
    }
  }
}
```

Restart Claude Desktop after saving.

## Tool Reference

### get_lists

Returns all task lists for the authenticated user.

```
get_lists()
→ [{"id": "MTIz...", "title": "My Tasks"}, {"id": "QWJj...", "title": "Work"}]
```

### create_task

Creates a new task or subtask.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | str | Yes | Task title (max 1024 chars) |
| `tasklist_id` | str | Yes | Target task list ID |
| `notes` | str | No | Task description |
| `due_date` | str | No | Due date in `YYYY-MM-DD` format |
| `parent` | str | No | Parent task ID (creates a subtask) |

```
# Create a regular task
create_task(title="Buy groceries", tasklist_id="MTIz...", due_date="2026-03-01")

# Create a subtask
create_task(title="Buy milk", tasklist_id="MTIz...", parent="<parent_task_id>")
```

### list_tasks

Lists tasks from a task list with optional filtering.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tasklist_id` | str | Yes | Task list ID |
| `show_completed` | bool | No | Include completed tasks (default: `false`) |
| `show_hidden` | bool | No | Include hidden tasks (default: `false`) |
| `max_results` | int | No | Max tasks to return (default: `100`, max: `100`) |

Each returned task includes an `is_subtask` boolean derived from the presence of a `parent` field.

### complete_task

Toggles task completion status.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tasklist_id` | str | Yes | Task list ID |
| `task_id` | str | Yes | Task ID |
| `completed` | bool | Yes | `true` = mark completed, `false` = mark as needs action |

When marking a task as completed, a timestamp is automatically set. When marking as incomplete, the timestamp is cleared.

### add_link

Adds a web link to a task's notes field using Markdown formatting.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tasklist_id` | str | Yes | Task list ID |
| `task_id` | str | Yes | Task ID |
| `url` | str | Yes | URL (must start with `http://` or `https://`) |
| `label` | str | No | Display label (defaults to the URL) |

Links are appended to a `Links:` section at the end of the task's notes:

```
Original task notes here...

Links:
- [JIRA-123](https://jira.company.com/browse/JIRA-123)
- [PR #456](https://github.com/org/repo/pull/456)
- [https://github.com/org/repo](https://github.com/org/repo)
```

## Known Limitations

These are Google Tasks API constraints, not server limitations:

- **Date-only due dates** -- Only `YYYY-MM-DD` dates are supported. Specific times are ignored by the API.
- **No recurring tasks** -- The API does not expose recurrence functionality.
- **Max 100 tasks per request** -- `list_tasks` returns at most 100 tasks per call.
- **Links in notes** -- The API `links` field is read-only, so links are stored as formatted text in the notes field.

## Troubleshooting

**`credentials.json not found`**
Download OAuth client credentials from the Google Cloud Console and save the file as `credentials.json` in the project root directory (next to `pyproject.toml`).

**`Authentication failed` / tools return auth errors**
Delete `token.json` from the project root and restart the server to trigger a fresh OAuth consent flow.

**`Rate limit exceeded`**
The Google Tasks API has usage quotas. Wait a moment and retry.

**OAuth consent screen shows "unverified app"**
This is expected during development. Click **Advanced**, then **Go to \<app name\>** to proceed.

**Server not appearing in MCP client**
- Verify the `server.py` path in the config is absolute.
- Run `python3 gtasks_mcp_server/server.py` manually to check for errors.

## License

See [LICENSE](LICENSE) for details.
