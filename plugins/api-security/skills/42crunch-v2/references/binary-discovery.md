# Binary Discovery

## Purpose

Locate the `42c-ast` binary silently across all supported IDEs. Produce no
output to the user during discovery. Return only the resolved binary path for
use in subsequent commands.

---

## Priority Order

Stop at the first successful match.

### Step 0 — Persistent cache (check first)

```bash
# macOS / Linux
if [ -f ~/.42crunch/.resolved-binary ]; then
  CACHED=$(cat ~/.42crunch/.resolved-binary)
  test -x "$CACHED" && echo "$CACHED"
fi
```

If the file exists and the path inside points to an executable, use that path
immediately — skip Steps 1–3.

### Step 1 — Canonical install location

The 42Crunch extension installs the binary here on first run, regardless of
which IDE is used.

| OS            | Path                                      |
|---------------|-------------------------------------------|
| macOS / Linux | `~/.42crunch/bin/42c-ast`                 |
| Windows       | `%USERPROFILE%\.42crunch\bin\42c-ast.exe` |

Check with:

```bash
# macOS / Linux
test -x ~/.42crunch/bin/42c-ast && echo ~/.42crunch/bin/42c-ast

# Windows (PowerShell)
if (Test-Path "$env:USERPROFILE\.42crunch\bin\42c-ast.exe") { "$env:USERPROFILE\.42crunch\bin\42c-ast.exe" }
```

### Step 2 — System PATH

```bash
command -v 42c-ast 2>/dev/null
```

### Step 3 — IDE extensions directories (last resort, scan concurrently)

Search all directories in the table below that exist on the current machine.

| IDE              | macOS                                                                | Linux                                              | Windows                                                     |
|------------------|----------------------------------------------------------------------|----------------------------------------------------|-------------------------------------------------------------|
| VS Code          | `~/Library/Application Support/Code/Extensions/`                    | `~/.vscode/extensions/`                            | `%USERPROFILE%\.vscode\extensions\`                         |
| VS Code Insiders | `~/Library/Application Support/Code - Insiders/Extensions/`         | `~/.vscode-insiders/extensions/`                   | `%USERPROFILE%\.vscode-insiders\extensions\`                |
| Cursor           | `~/Library/Application Support/Cursor/Extensions/`                  | `~/.cursor/extensions/`                            | `%USERPROFILE%\.cursor\extensions\`                         |
| Windsurf         | `~/Library/Application Support/Windsurf/Extensions/`                | `~/.windsurf/extensions/`                          | `%USERPROFILE%\.windsurf\extensions\`                       |
| IntelliJ IDEA    | `~/Library/Application Support/JetBrains/IntelliJIdea*/plugins/`    | `~/.local/share/JetBrains/IntelliJIdea*/plugins/`  | `%APPDATA%\JetBrains\IntelliJIdea*\plugins\`                |
| IntelliJ IDEA CE | `~/Library/Application Support/JetBrains/IdeaIC*/plugins/`          | `~/.local/share/JetBrains/IdeaIC*/plugins/`        | `%APPDATA%\JetBrains\IdeaIC*\plugins\`                      |
| WebStorm         | `~/Library/Application Support/JetBrains/WebStorm*/plugins/`        | `~/.local/share/JetBrains/WebStorm*/plugins/`      | `%APPDATA%\JetBrains\WebStorm*\plugins\`                    |
| GoLand           | `~/Library/Application Support/JetBrains/GoLand*/plugins/`          | `~/.local/share/JetBrains/GoLand*/plugins/`        | `%APPDATA%\JetBrains\GoLand*\plugins\`                      |
| Eclipse          | `~/eclipse/plugins/`                                                 | `~/eclipse/plugins/`                               | `%USERPROFILE%\eclipse\plugins\`                            |
| Eclipse (shared) | `/opt/eclipse/plugins/`                                              | `/opt/eclipse/plugins/`                            | `C:\Eclipse\plugins\`                                       |

For each candidate directory that exists, search recursively:

```bash
find <dir> \( -name "42c-ast" -o -name "42c-ast.exe" \) 2>/dev/null | head -1
```

---

### After successful discovery (Steps 1–3)

Write the resolved path to the persistent cache so future runs skip discovery:

```bash
echo "<resolved-path>" > ~/.42crunch/.resolved-binary
```

The `~/.42crunch/` directory is created by the 42Crunch extension and already
exists on any machine where the extension is installed.

---

## Failure Handling

Only if all steps above are exhausted without a match, surface this message:

> "The `42c-ast` binary could not be found. Please install the 42Crunch
> OpenAPI Editor extension for your IDE (VS Code, IntelliJ, or Eclipse) and
> restart. The extension bundles and installs the binary automatically."

Then stop. Do not attempt any audit or scan commands without a resolved binary.
