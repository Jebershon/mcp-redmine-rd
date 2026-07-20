# mcp-redmine-rd — Redmine MCP for Claude Code

Brings [Redmine](https://www.redmine.org/) bug tickets — description, comments,
custom fields, and **screenshots as viewable images** — into Claude Code, and
ships a `/fix-bug` skill that drives a ticket to a verified fix. Built with
[FastMCP 3](https://github.com/jlowin/fastmcp).

It authenticates to Redmine with your own API key, needs **no admin rights**, and
launches over stdio so your MCP client starts it on demand. Each developer runs it
with their own key, so every read and write to the tracker is attributed to them.

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

## Install from PyPI (developers)

Once published, developers install it without cloning:

```bash
pipx install mcp-redmine-rd          # isolated global install (recommended)
# or:  pip install mcp-redmine-rd
```

Then register it with Claude Code — each developer uses their own API key:

```bash
claude mcp add redmine --scope user \
  --env REDMINE_URL=https://tracker.rapiddata.com \
  --env REDMINE_API_KEY=<your-key> \
  -- mcp-redmine-rd-local
```

`pipx` keeps the tool in its own environment and puts `mcp-redmine-rd-local` on
`PATH`, so the command resolves from any project.

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

### A developer's one-time setup

**Prerequisites:** Python 3.11+, `git`, and [Claude Code](https://claude.com/claude-code).
Check Python with `python --version` (use `python3` on macOS/Linux if `python`
points at 2.x).

**1. Clone the repo and enter it**

```bash
git clone https://github.com/Jebershon/mcp-redmine-rd.git
cd mcp-redmine-rd
```

**2. Create and activate a virtual environment**

A venv keeps this project's dependencies isolated. Activating it also puts the
`mcp-redmine-rd-local` command on your `PATH`, which `.mcp.json` needs.

```bash
python -m venv .venv
```

Activate it — pick the line for your shell:

```bash
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell
source .venv/Scripts/activate    # Windows Git Bash
```

Your prompt should now show `(.venv)`.

**3. Install the server**

```bash
pip install -e .
```

Confirm the launch command is available (this is what `.mcp.json` runs):

```bash
mcp-redmine-rd-local --help  ||  echo "not on PATH — is the venv active?"
```

**4. Get your personal Redmine API key**

In Redmine (`https://tracker.rapiddata.com`): click your name (top right) →
**My account** → in the right sidebar, **API access key** → **Show**. Copy the
40-character key. It acts as your account — treat it like a password.

**5. Create your `.env` file**

The server reads your key from a local `.env` that is **gitignored** — it is never
committed and never shared. `REDMINE_URL` already comes from `.mcp.json`, so `.env`
only needs your key:

```bash
cp .env.example .env
```

Open `.env` and set:

```
REDMINE_API_KEY=<paste-your-40-char-key>
```

**6. Verify it works (optional but recommended)**

Run the test suite to confirm the install is healthy:

```bash
pip install pytest pytest-asyncio
pytest -q
```

**7. Open the repo in Claude Code**

Launch Claude Code **from this repo directory, with the venv still active** (so the
command is on `PATH`):

```bash
claude
```

Claude Code reads `.mcp.json`, starts the `redmine` server over stdio on demand, and
the tools plus the `/fix-bug` skill become available. Verify inside Claude Code with
`/mcp` — you should see `redmine` connected — then try `/fix-bug <an issue number>`.

> **If `redmine` doesn't connect**, the `mcp-redmine-rd-local` command isn't on
> `PATH` — you most likely launched Claude Code without the venv active. Either
> activate the venv first, or edit `.mcp.json`'s `command` to the script's absolute
> path (`.venv/Scripts/mcp-redmine-rd-local.exe` on Windows,
> `.venv/bin/mcp-redmine-rd-local` on macOS/Linux).

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `REDMINE_URL` | Yes | — | Base URL of your Redmine instance |
| `REDMINE_API_KEY` | Yes | — | Your personal Redmine API key (My account → API access key). |
| `MCP_LOCAL_TOKEN` | No | `local` | Bearer token the MCP client presents in **HTTP** mode (ignored over stdio) |
| `MCP_HOST` | No | `127.0.0.1` | Bind host (HTTP mode) |
| `MCP_PORT` | No | `8000` | Bind port |
| `CORS_ALLOW_ORIGINS` | No | `*` | Comma-separated allowed origins. Narrow this for a shared deployment. |

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

The "Redmine permission" column is what your API key's account role must grant — a
tool returns a descriptive error if your account lacks the permission.

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

## Connect Claude Code automatically

Opening **this repo** in Claude Code connects the server automatically via
`.mcp.json` — nothing else to do.

To make the `redmine` tools available in **every** project (not just this repo),
register the server once at user scope. With the venv active, run:

```bash
claude mcp add redmine --scope user \
  --env REDMINE_URL=https://tracker.rapiddata.com \
  --env REDMINE_API_KEY=<your-40-char-key> \
  -- mcp-redmine-rd-local
```

Claude Code now starts the server on demand in any project. Confirm with:

```bash
claude mcp list        # should show: redmine
```

or `/mcp` inside a Claude Code session (look for `redmine` connected). Remove it
again any time with `claude mcp remove redmine --scope user`.

> The `command` (`mcp-redmine-rd-local`) must be resolvable when Claude Code
> launches it. If you registered it from a venv, keep that venv active, or use the
> script's absolute path in place of the bare command
> (`.venv/Scripts/mcp-redmine-rd-local.exe` on Windows,
> `.venv/bin/mcp-redmine-rd-local` on macOS/Linux).

## License

MIT — see [LICENSE](LICENSE). Forked from
[tuzumkuru/mcp-redmine-oauth](https://github.com/tuzumkuru/mcp-redmine-oauth).
