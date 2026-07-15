# Architecture — RapidData Redmine MCP

A single-user MCP server that bridges an MCP client (e.g. Claude Code) to a
Redmine instance, authenticating with the user's Redmine **API key**.

## Components

```
MCP Client (Claude Code, MCP Inspector, …)
        │  MCP over stdio (default) or Streamable HTTP
        ▼
┌───────────────────────────────────────────┐
│              FastMCP 3 server              │
│                                            │
│  Tools / Resources / Prompts               │──── REST API ───▶ Redmine
│  RedmineClient (pooled httpx)              │     X-Redmine-API-Key
│                                            │◀────────────────
└───────────────────────────────────────────┘
```

There is no OAuth and no token store. The API key is read from the environment
(`REDMINE_API_KEY`) and sent on every Redmine request by `RedmineClient`.

## Transports

- **stdio** (`main_local_stdio`) — the MCP client launches the server on demand.
  No port, no bearer. There is no HTTP auth layer, so a full-scope access token is
  injected into the tool modules (`_inject_local_token`) to satisfy the
  `@requires_scopes` decorators. This is the recommended way to run it, and what
  `.mcp.json` uses.
- **HTTP / Streamable HTTP** (`main`) — binds to `127.0.0.1` by default.
  `LocalTokenVerifier` gates access with a single pre-shared token
  (`MCP_LOCAL_TOKEN`) and grants all registered scopes.

## Modules

| Module | Responsibility |
|---|---|
| `server.py` | Config, FastMCP wiring, both entry points, lifespan (closes the client) |
| `client.py` | `RedmineClient` — pooled async httpx wrapper, API-key auth, typed errors, binary/attachment download |
| `tools.py` | Read/write issue, project, and wiki tools; issue formatting; screenshot handling; custom-field resolution |
| `images.py` | Downscale and re-encode attachment images before they are returned |
| `resources.py` | Reference resources (projects, trackers, statuses, priorities, current user) |
| `prompts.py` | `summarize_ticket`, `draft_bug_report` |
| `scopes.py` | Scope constants, the `@requires_scopes` decorator, and the scope registry. A scope names the Redmine permission a tool needs; in local mode the client is granted all of them (the API key already carries the user's Redmine role). |
| `auth.py` | `LocalTokenVerifier` for HTTP mode |

## Permissions

The API key inherits the Redmine role of the account that owns it. A tool that
calls an endpoint the account isn't permitted to use gets a Redmine `403`, which
`RedmineClient` raises and the `@requires_scopes` layer surfaces as a readable
error — the scope decorators document which permission each tool needs.
