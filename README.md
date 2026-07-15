# mcp-redmine-rd — Redmine MCP for Claude Code

Brings [Redmine](https://www.redmine.org/) bug tickets — description, comments,
custom fields, and **screenshots as viewable images** — into Claude Code, and
ships a `/fix-bug` skill that drives a ticket to a verified fix. Built with
[FastMCP 3](https://github.com/jlowin/fastmcp).

It runs in **single-user local mode**: it authenticates to Redmine with your own
API key, needs **no admin rights**, and launches over stdio so your MCP client
starts it on demand. Each developer runs it with their own key, so every read and
write to the tracker is attributed to them.

> A centralized multi-user OAuth mode is also supported but is not the default —
> see [Optional: OAuth mode](#optional-oauth-mode).

## How it works

```
MCP Client (Claude Code, MCP Inspector, …)
        │  MCP over stdio (launched on demand)
        ▼
┌───────────────────────────────────┐
│           mcp-redmine-rd          │
│  authenticates with your Redmine  │──── REST API ───▶ Redmine
│  API key (X-Redmine-API-Key)      │◀────────────────
│  Tools + /fix-bug skill           │
└───────────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- A Redmine instance with the **REST API enabled**
  (Administration → Settings → API → *Enable REST web service*)
- Your personal API key: **My account → API access key → Show**. No admin rights
  needed.

## Quickstart (local mode)

```bash
git clone https://github.com/Jebershon/mcp-redmine-rd.git
cd mcp-redmine-rd
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
# set REDMINE_URL and REDMINE_API_KEY in .env
```

Open the repo in Claude Code — `.mcp.json` launches the server over stdio
automatically, and the `redmine` tools plus `/fix-bug` are ready. Try `/fix-bug 1234`.

To run the server standalone over HTTP instead of stdio, `mcp-redmine-rd` serves
`http://127.0.0.1:8000/mcp`; point your client at it with header
`Authorization: Bearer <MCP_LOCAL_TOKEN>` (default `local`).

## Sharing with your team

The easiest way to give co-developers both the server and the `/fix-bug` skill is
**one git repo**. Committed to it are `.mcp.json` (wires up the MCP server) and
`.claude/skills/fix-bug/` (the skill). Secrets are **not**: each developer keeps
their own API key in a gitignored `.env`.

`.mcp.json` launches the server over **stdio**, so there is no port to manage and
no server to start by hand:

```json
{
  "mcpServers": {
    "redmine": {
      "command": "mcp-redmine-rd-local",
      "env": { "REDMINE_URL": "https://tracker.rapiddata.com" }
    }
  }
}
```

A developer's one-time setup:

```bash
git clone https://github.com/Jebershon/mcp-redmine-rd.git && cd mcp-redmine-rd
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
printf 'REDMINE_API_KEY=<their-own-key>\n' >> .env   # from My account → API access key
```

Open the repo in Claude Code (from the activated venv so the `mcp-redmine-rd-local`
command is on `PATH`). The `redmine` server connects automatically and `/fix-bug`
is available.

> Prefer not to depend on the venv being active? Point the `.mcp.json` command at
> the absolute path of the installed script (`.venv/Scripts/mcp-redmine-rd-local`
> on Windows, `.venv/bin/mcp-redmine-rd-local` elsewhere).

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `REDMINE_URL` | Yes | — | Base URL of your Redmine instance |
| `REDMINE_API_KEY` | Yes (local mode) | — | Your Redmine API key. Setting it selects local mode. |
| `MCP_LOCAL_TOKEN` | No | `local` | Bearer token the MCP client presents in local **HTTP** mode |
| `MCP_HOST` | No | `127.0.0.1` (local) | Bind host |
| `MCP_PORT` | No | `8000` | Bind port |
| `TOKEN_CACHE_TTL_SECONDS` | No | `60` | How long a verified token is trusted before re-checking with Redmine. `0` disables caching. |
| `CORS_ALLOW_ORIGINS` | No | `*` | Comma-separated allowed origins. Narrow this for a shared deployment. |

OAuth-mode variables (`REDMINE_CLIENT_ID`, `REDMINE_CLIENT_SECRET`,
`MCP_BASE_URL`, `REDMINE_SCOPES`) are described under
[Optional: OAuth mode](#optional-oauth-mode).

## Available tools & resources

| Component | Type | Redmine permission | Description |
|---|---|---|---|
| `get_issue_details` | Tool | `view_issues` | Fetch an issue by ID with description, custom fields, journals, and **attached screenshots as viewable images** |
| `get_issue_attachment` | Tool | `view_issues` | View a single attachment at full resolution |
| `search_issues` | Tool | `view_issues`, `search_project` | Full-text search across issues with pagination |
| `list_issues` | Tool | `view_issues` | List issues with filters (project, assignee, status, tracker, sort) |
| `get_issue_relations` | Tool | `view_issues` | Get issue relations (blocking, blocked-by, related, etc.) |
| `get_project_details` | Tool | `view_project` | Project details with trackers, categories, and enabled modules |
| `get_project_versions` | Tool | `view_project` | Project versions/milestones with status and due dates |
| `list_time_entries` | Tool | `view_time_entries` | List time entries with filters (project, user, date range) |
| `create_issue` | Tool | `add_issues` | Create a new issue with subject, tracker, priority, assignee, custom fields, etc. |
| `update_issue` | Tool | `edit_issues` | Update an existing issue (status, assignee, notes, custom fields, etc.) |
| `create_project` | Tool | `add_project` | Create a new Redmine project, with custom fields |
| `update_project` | Tool | `edit_project` | Update project name, description, visibility, trackers, custom fields |
| `get_wiki_page` | Tool | `view_wiki_pages` | Get a wiki page from a project |
| `update_wiki_page` | Tool | `edit_wiki_pages` | Create or update a wiki page |
| `rename_wiki_page` | Tool | `rename_wiki_pages` | Rename a wiki page with optional redirect |
| `summarize_ticket` | Prompt | `view_issues` | Generate a concise summary of an issue with next steps |
| `draft_bug_report` | Prompt | `view_project` | Draft a structured bug report from rough notes |
| `redmine://projects/active` | Resource | `view_project` | List active projects |
| `redmine://trackers` | Resource | `view_project` | List available trackers |
| `redmine://issue-statuses` | Resource | `view_issues` | All issue statuses with IDs and closed flags |
| `redmine://enumerations/priorities` | Resource | `view_issues` | Issue priority levels with IDs |
| `redmine://users/me` | Resource | _(auth only)_ | Current authenticated user profile |

In local mode the "Redmine permission" column is whatever your API key's account
role already grants — a tool returns a descriptive error if your account lacks the
permission. (In OAuth mode the same column is the granted scope.)

Planned: attachment upload, structured logging.

### Custom fields

`create_issue`, `update_issue`, `create_project`, and `update_project` accept a
`custom_fields` map keyed by **field name or numeric field ID**:

```json
{"Severity": "High", "Affected version": "2.4.1", "7": ["iOS", "Android"]}
```

Use a list for multi-value fields. Booleans are encoded as Redmine expects them
(`"1"` / `"0"`, not `"true"` / `"false"`). On update, only the fields you pass are
touched — the rest keep their current values.

Name resolution calls `/custom_fields.json`, **which Redmine restricts to admins**.
For a non-admin user, names cannot be resolved and the tool says so, telling the
caller to pass numeric IDs instead. Those IDs are listed next to each custom field
by `get_issue_details` and `get_project_details`, so the workflow still closes
without admin rights. The name→ID map is cached for 10 minutes once fetched.

### Screenshots

`get_issue_details` returns image content blocks for any image attached to the
issue — including images added in later comments, which is usually where the useful
screenshot lives. Images are downscaled to 1500px on the long edge and re-encoded
as PNG before being returned; a 3000×2000 screenshot comes back at roughly a quarter
of its original size. At most four are inlined per call (the most recent ones); the
rest are listed by name and can be fetched individually with `get_issue_attachment`.

An attachment that is missing, oversized, or undecodable degrades to a text note —
it never fails the whole call.

## The `/fix-bug` skill

[`.claude/skills/fix-bug/SKILL.md`](.claude/skills/fix-bug/SKILL.md) drives the full
loop: read the ticket and its screenshots → locate the cause → reproduce → fix →
verify → report back to the ticket. The MCP server is the plumbing; the skill is
what makes a bug fix fast.

When you open this repo in Claude Code, the skill is picked up automatically. To use
it while working in a **different** repository, copy it there:

```bash
mkdir -p your-app/.claude/skills
cp -r .claude/skills/fix-bug your-app/.claude/skills/
```

Then `/fix-bug 1234`, or just "fix #1234".

The skill will not write to Redmine without asking, and will not close a ticket on
its own. It also treats issue text as untrusted input — anyone who can file a bug
can write instructions aimed at the model in the repro steps.

## Optional: OAuth mode

For a shared, multi-user deployment you can run the server centrally with Redmine
OAuth instead of per-developer API keys. This needs an admin to register an OAuth
application in Redmine; individual developers then authorize through Redmine and
never handle API keys.

1. **Register an OAuth application**: Administration → Applications → New
   Application. Set the Redirect URI to `http://<MCP_BASE_URL>/auth/callback`, mark
   it a confidential client, and enable the scopes listed below. Copy the generated
   **Client ID** and **Client Secret**.
2. **Configure** `.env` with `REDMINE_CLIENT_ID` and `REDMINE_CLIENT_SECRET` (leave
   `REDMINE_API_KEY` unset), plus `MCP_BASE_URL` (the externally reachable URL).
3. **Run**: `mcp-redmine-rd` (HTTP on `MCP_PORT`), or `docker compose up --build`.

Scopes to enable on the OAuth application, by the tools that use them:

| Redmine permission | Scope | Used by |
|---|---|---|
| View projects | `view_project` | project reads, `redmine://projects/active`, `redmine://trackers`, `draft_bug_report` |
| Search projects | `search_project` | `search_issues` |
| Create / Edit project | `add_project`, `edit_project` | `create_project`, `update_project` |
| View issues | `view_issues` | issue reads, statuses, priorities, `summarize_ticket` |
| Add / Edit issues | `add_issues`, `edit_issues` | `create_issue`, `update_issue` |
| View spent time | `view_time_entries` | `list_time_entries` |
| View / Edit / Rename wiki | `view_wiki_pages`, `edit_wiki_pages`, `rename_wiki_pages` | wiki tools |

If your OAuth app enables only a subset, set `REDMINE_SCOPES` (space-separated) so
authorization requests only those; tools whose scopes aren't covered return a
descriptive error at call time instead of breaking the whole flow. See
[docs/architecture.md](docs/architecture.md) for the OAuth flow and token handling.

## License

MIT — see [LICENSE](LICENSE). Forked from
[tuzumkuru/mcp-redmine-oauth](https://github.com/tuzumkuru/mcp-redmine-oauth).
