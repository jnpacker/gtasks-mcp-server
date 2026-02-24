"""Google Tasks MCP Server.

An MCP server that provides tools for managing Google Tasks,
including creating tasks, listing tasks, completing tasks, and adding links.
"""

import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional

from fastmcp import FastMCP
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# ---------------------------------------------------------------------------
# Logging – all output goes to stderr so stdout stays clean for MCP protocol
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("gtasks-mcp-server")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/tasks"]
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_PATH = os.path.join(_PROJECT_ROOT, "credentials.json")
TOKEN_PATH = os.path.join(_PROJECT_ROOT, "token.json")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RE = re.compile(r"^https?://\S+$")

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class GTasksError(Exception):
    """Base exception for Google Tasks MCP server."""


class AuthenticationError(GTasksError):
    """Raised when authentication fails or credentials are missing."""


class ValidationError(GTasksError):
    """Raised when input validation fails."""


class APIError(GTasksError):
    """Raised when the Google Tasks API returns an error."""


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------

def validate_date_format(date_str: str) -> None:
    """Validate that a date string matches YYYY-MM-DD format."""
    if not DATE_RE.match(date_str):
        raise ValidationError(
            f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD."
        )
    # Also validate it's a real date
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError(f"Invalid date: '{date_str}'. {exc}") from exc


def validate_url_format(url: str) -> None:
    """Validate that a URL starts with http:// or https://."""
    if not URL_RE.match(url):
        raise ValidationError(
            f"Invalid URL format: '{url}'. URL must start with http:// or https://."
        )


# ---------------------------------------------------------------------------
# Error Handling Helpers
# ---------------------------------------------------------------------------

def handle_api_error(error: HttpError, context: str) -> None:
    """Convert Google API HttpError into an appropriate GTasksError.

    Raises:
        AuthenticationError: For 401/403 responses.
        APIError: For all other HTTP error responses.
    """
    status = error.resp.status
    if status in (401, 403):
        raise AuthenticationError(
            f"Authentication failed during {context}. "
            "Please re-authenticate with Google Tasks."
        ) from error
    if status == 404:
        raise APIError(f"Resource not found during {context}.") from error
    if status == 429:
        raise APIError(
            f"Rate limit exceeded during {context}. Try again later."
        ) from error
    if status >= 500:
        raise APIError(
            f"Google Tasks API temporarily unavailable during {context}."
        ) from error
    raise APIError(
        f"Google Tasks API error during {context}: {error}"
    ) from error


def handle_unexpected_error(error: Exception, operation: str) -> None:
    """Handle unexpected non-HTTP errors.

    Raises:
        GTasksError: Always.
    """
    logger.exception("Unexpected error during %s", operation)
    raise GTasksError(
        f"Unexpected error during {operation}: {error}"
    ) from error


# ---------------------------------------------------------------------------
# Response Sanitization
# ---------------------------------------------------------------------------

_TASK_FIELDS = {"id", "title", "notes", "due", "status", "parent", "updated", "completed"}


def sanitize_task_response(task: dict) -> dict:
    """Return only the relevant fields from a task resource."""
    result = {k: task[k] for k in _TASK_FIELDS if k in task}
    result["is_subtask"] = "parent" in task
    return result


def sanitize_tasklist_response(tasklist: dict) -> dict:
    """Return only id and title from a tasklist resource."""
    return {"id": tasklist["id"], "title": tasklist["title"]}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

_service_cache = None


def get_authenticated_service():
    """Build and return an authenticated Google Tasks API service.

    On first run, opens a browser for OAuth consent.  On subsequent runs,
    reuses / refreshes the stored token.

    Raises:
        AuthenticationError: If credentials are missing or the flow fails.
    """
    global _service_cache
    if _service_cache is not None:
        return _service_cache

    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            logger.warning("Failed to load token.json; will re-authenticate.")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                logger.warning("Token refresh failed: %s", exc)
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_PATH):
                raise AuthenticationError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Download OAuth client credentials from the Google Cloud Console."
                )
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)
            except Exception as exc:
                raise AuthenticationError(
                    f"OAuth consent flow failed: {exc}"
                ) from exc

        # Persist token for future runs
        try:
            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())
            os.chmod(TOKEN_PATH, 0o600)
        except OSError as exc:
            logger.warning("Could not save token.json: %s", exc)

    service = build("tasks", "v1", credentials=creds)
    _service_cache = service
    return service


# ---------------------------------------------------------------------------
# FastMCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("Google Tasks")


# ---------------------------------------------------------------------------
# Tool: get_lists
# ---------------------------------------------------------------------------
@mcp.tool()
def get_lists() -> list[dict]:
    """Get all Google Tasks task lists for the authenticated user.

    Returns a list of task lists, each with 'id' and 'title' fields.
    """
    try:
        service = get_authenticated_service()
        results = service.tasklists().list().execute()
        items = results.get("items", [])
        return [sanitize_tasklist_response(tl) for tl in items]
    except GTasksError:
        raise
    except HttpError as exc:
        handle_api_error(exc, "get_lists")
    except Exception as exc:
        handle_unexpected_error(exc, "get_lists")


# ---------------------------------------------------------------------------
# Tool: create_task
# ---------------------------------------------------------------------------
@mcp.tool()
def create_task(
    title: str,
    tasklist_id: str,
    notes: Optional[str] = None,
    due_date: Optional[str] = None,
    parent: Optional[str] = None,
) -> dict:
    """Create a new task (or subtask) in a Google Tasks list.

    Args:
        title: Task title (max 1024 characters).
        tasklist_id: ID of the target task list (from get_lists).
        notes: Optional notes / description for the task.
        due_date: Optional due date in YYYY-MM-DD format.
        parent: Optional parent task ID to create this as a subtask.

    Returns:
        The created task with id, title, notes, due, status, and parent fields.
    """
    # -- validation --
    if not title or not title.strip():
        raise ValidationError("Task title must not be empty.")
    if len(title) > 1024:
        raise ValidationError("Task title must be 1024 characters or fewer.")
    if due_date is not None:
        validate_date_format(due_date)

    body: dict = {"title": title.strip()}
    if notes is not None:
        body["notes"] = notes
    if due_date is not None:
        body["due"] = f"{due_date}T00:00:00.000Z"

    try:
        service = get_authenticated_service()
        kwargs: dict = {"tasklist": tasklist_id, "body": body}
        if parent is not None:
            kwargs["parent"] = parent
        result = service.tasks().insert(**kwargs).execute()
        return sanitize_task_response(result)
    except GTasksError:
        raise
    except HttpError as exc:
        handle_api_error(exc, "create_task")
    except Exception as exc:
        handle_unexpected_error(exc, "create_task")


# ---------------------------------------------------------------------------
# Tool: list_tasks
# ---------------------------------------------------------------------------
@mcp.tool()
def list_tasks(
    tasklist_id: str,
    show_completed: bool = False,
    show_hidden: bool = False,
    max_results: int = 100,
) -> list[dict]:
    """List tasks from a Google Tasks task list.

    Args:
        tasklist_id: ID of the task list to retrieve tasks from.
        show_completed: If True, include completed tasks. Defaults to False.
        show_hidden: If True, include hidden tasks. Defaults to False.
        max_results: Maximum number of tasks to return (max 100).

    Returns:
        A list of tasks with id, title, notes, due, status, parent,
        updated, completed, and is_subtask fields.
    """
    if max_results < 1:
        max_results = 1
    if max_results > 100:
        max_results = 100

    try:
        service = get_authenticated_service()
        results = (
            service.tasks()
            .list(
                tasklist=tasklist_id,
                showCompleted=show_completed,
                showHidden=show_hidden,
                maxResults=max_results,
            )
            .execute()
        )
        items = results.get("items", [])
        return [sanitize_task_response(t) for t in items]
    except GTasksError:
        raise
    except HttpError as exc:
        handle_api_error(exc, "list_tasks")
    except Exception as exc:
        handle_unexpected_error(exc, "list_tasks")


# ---------------------------------------------------------------------------
# Tool: complete_task
# ---------------------------------------------------------------------------
@mcp.tool()
def complete_task(
    tasklist_id: str,
    task_id: str,
    completed: bool,
) -> dict:
    """Toggle task completion status.

    Args:
        tasklist_id: ID of the task list containing the task.
        task_id: ID of the task to update.
        completed: True to mark as completed, False to mark as needs action.

    Returns:
        The updated task with id, title, status, and completed fields.
    """
    try:
        service = get_authenticated_service()

        # Fetch the current task so we send a full resource to update()
        current = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()

        if completed:
            current["status"] = "completed"
            current["completed"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.000Z"
            )
        else:
            current["status"] = "needsAction"
            current.pop("completed", None)

        result = (
            service.tasks()
            .update(tasklist=tasklist_id, task=task_id, body=current)
            .execute()
        )
        return sanitize_task_response(result)
    except GTasksError:
        raise
    except HttpError as exc:
        handle_api_error(exc, "complete_task")
    except Exception as exc:
        handle_unexpected_error(exc, "complete_task")


# ---------------------------------------------------------------------------
# Tool: add_link
# ---------------------------------------------------------------------------
@mcp.tool()
def add_link(
    tasklist_id: str,
    task_id: str,
    url: str,
    label: Optional[str] = None,
) -> dict:
    """Add a web link to a task's notes field.

    Links are stored in a 'Links:' section at the end of the notes using
    Markdown-style formatting.  Useful for attaching Jira issues, pull
    requests, repository URLs, etc.

    Args:
        tasklist_id: ID of the task list containing the task.
        task_id: ID of the task to add the link to.
        url: Web URL to add (must start with http:// or https://).
        label: Optional display label for the link. Defaults to the URL.

    Returns:
        The updated task with the modified notes field.
    """
    validate_url_format(url)

    link_label = label if label else url
    link_entry = f"- [{link_label}]({url})"

    try:
        service = get_authenticated_service()

        # Fetch current task to preserve existing notes
        current = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
        current_notes = current.get("notes", "")

        if "Links:" in current_notes:
            updated_notes = f"{current_notes}\n{link_entry}"
        else:
            separator = "\n\n" if current_notes else ""
            updated_notes = f"{current_notes}{separator}Links:\n{link_entry}"

        current["notes"] = updated_notes

        result = (
            service.tasks()
            .update(tasklist=tasklist_id, task=task_id, body=current)
            .execute()
        )
        return sanitize_task_response(result)
    except GTasksError:
        raise
    except HttpError as exc:
        handle_api_error(exc, "add_link")
    except Exception as exc:
        handle_unexpected_error(exc, "add_link")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--auth":
        print("Authenticating with Google Tasks...")
        service = get_authenticated_service()
        # Quick smoke test: list task lists
        results = service.tasklists().list().execute()
        items = results.get("items", [])
        print(f"Authenticated successfully. Found {len(items)} task list(s):")
        for tl in items:
            print(f"  - {tl['title']} ({tl['id']})")
    else:
        mcp.run()
