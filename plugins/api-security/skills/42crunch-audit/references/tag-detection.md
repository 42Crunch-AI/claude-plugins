# Tag Detection

## Purpose

Silently resolve the 42Crunch platform tag associated with the OAS file.
Announce the result to the user. Use the tag in the audit command flags.

**Freemium mode**: skip this entire file — tag detection requires platform
access and freemium tokens have none. Proceed directly to the audit or scan
workflow without `--tag` or `--report-sqg`.

---

## Step 1 — SQLite Workspace Database (VS Code variants)

Before running the database query, announce to the user:
> "Looking for your platform tag..."

Do not announce each individual database file checked.

The 42Crunch VS Code extension stores tag associations in the IDE's SQLite
workspace state database. Query all matching `state.vscdb` files across every
VS Code-family IDE that may be installed.

| IDE              | macOS                                                                           | Linux                                                              | Windows                                                                   |
|------------------|---------------------------------------------------------------------------------|--------------------------------------------------------------------|---------------------------------------------------------------------------|
| VS Code          | `~/Library/Application Support/Code/User/workspaceStorage/*/state.vscdb`       | `~/.config/Code/User/workspaceStorage/*/state.vscdb`               | `%APPDATA%\Code\User\workspaceStorage\*\state.vscdb`                      |
| VS Code Insiders | `~/Library/Application Support/Code - Insiders/User/workspaceStorage/*/state.vscdb` | `~/.config/Code - Insiders/User/workspaceStorage/*/state.vscdb` | `%APPDATA%\Code - Insiders\User\workspaceStorage\*\state.vscdb`          |
| Cursor           | `~/Library/Application Support/Cursor/User/workspaceStorage/*/state.vscdb`     | `~/.config/Cursor/User/workspaceStorage/*/state.vscdb`             | `%APPDATA%\Cursor\User\workspaceStorage\*\state.vscdb`                    |
| Windsurf         | `~/Library/Application Support/Windsurf/User/workspaceStorage/*/state.vscdb`   | `~/.config/Windsurf/User/workspaceStorage/*/state.vscdb`           | `%APPDATA%\Windsurf\User\workspaceStorage\*\state.vscdb`                  |

Run this Python snippet to query all databases:

```python
import json, os, glob, shutil, subprocess

oas_file = '<ABSOLUTE_PATH_TO_OAS_FILE>'  # substitute the real path

found_tag = None

if shutil.which('sqlite3') is None:
    pass  # sqlite3 not available — skipping workspace DB query
else:
    ws_dirs = [
        os.path.expanduser('~/Library/Application Support/Code/User/workspaceStorage'),
        os.path.expanduser('~/Library/Application Support/Code - Insiders/User/workspaceStorage'),
        os.path.expanduser('~/Library/Application Support/Cursor/User/workspaceStorage'),
        os.path.expanduser('~/Library/Application Support/Windsurf/User/workspaceStorage'),
        os.path.expanduser('~/.config/Code/User/workspaceStorage'),
        os.path.expanduser('~/.config/Code - Insiders/User/workspaceStorage'),
        os.path.expanduser('~/.config/Cursor/User/workspaceStorage'),
        os.path.expanduser('~/.config/Windsurf/User/workspaceStorage'),
    ]
    for ws_dir in ws_dirs:
        if not os.path.exists(ws_dir):
            continue
        for db in glob.glob(f'{ws_dir}/*/state.vscdb'):
            try:
                r = subprocess.run(
                    ['sqlite3', db,
                     "SELECT value FROM ItemTable WHERE key='42Crunch.vscode-openapi';"],
                    capture_output=True, text=True, timeout=5)
                val = r.stdout.strip()
                if not val:
                    continue
                data = json.loads(val)
                tags = data.get('openapi-42crunch.environment-tags-data', {}).get(oas_file, [])
                if tags:
                    found_tag = f"{tags[0]['categoryName']}:{tags[0]['tagName']}"
                    break
            except Exception:
                continue
        if found_tag:
            break
```

---

## Step 2 — Project Config File Fallback

If no tag was found in Step 1, check for a project-level config file relative
to the project root:

- `.42c/conf.yaml` — look for a `tag:` key

Parse the file if it exists and extract the tag string in `<category>:<tagname>` format.

---

## Step 3 — Announce the Result

### Tag found

> "This API is tagged on the 42Crunch platform as **`<category>:<tagname>`**.
> The audit will run against this tag, which means platform SQGs,
> customisations, and data dictionaries associated with it will be applied
> automatically."

Set the following audit flags: `--tag <category>:<tagname>`, `--report-sqg`.

### Tag not found

> "This API doesn't have a 42Crunch platform tag yet, so the audit can't apply
> your organisation's Security Quality Gates, data dictionaries, or
> customisations.
>
> Here's how to assign a tag in about 30 seconds:
> 1. Open the 42Crunch extension panel in your IDE (the shield icon in the sidebar).
> 2. Find this file in the API list — `<filename>`.
> 3. Click **Assign Tag**, choose the category and tag that matches this API, and save.
>
> Once the tag is saved, run this skill again and it will pick up the tag
> automatically. If you don't see any tags in the list, ask your 42Crunch
> platform administrator to create one."

**Stop.** Do not run any audit or scan commands. Do not fall back to running
without a tag.
