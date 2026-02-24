"""Entry point for `python -m gtasks_mcp_server.main`."""

from gtasks_mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run()
