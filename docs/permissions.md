# Permissions

**Status:** shipped · **Layer:** 6 · **Files:** `permissions.py`, `agent.py`, `resolve_path.py`, `__main__.py`
**Verified:** 2026-10-30

One gate in front of every registered tool. It answers `allow`, `ask`, or
`deny`; the loop applies the answer; the tool never sees a permission call. It
gates calls, not effects: a command the user allows can still change anything
the process can reach.

## Contract

### The rules

`permissions.RULES` is the whole default policy, in order:

```python
RULES = (
    ("read", "*", "allow"),
    ("read", "*.env", "ask"),
    ("read", "*.env.*", "ask"),
    ("read", "*.env.example", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "allow"),
    ("shell", "*", "allow"),
    ("shell", "*.env*", "ask"),
    ("external_directory", "*", "ask"),
)
```

The last matching rule wins. No rule means `deny`. A key that appears in no rule
cannot be allowed by a broader one, because matching is per key.

| Key | Value it sees | What it governs |
|---|---|---|
| `read` | the resolved path, for a `.env` check | `read`, and any tool given a `.env` path |
| `edit` | the `path` argument | `write` and `edit` |
| `glob` | the glob pattern, not the search root | `glob` |
| `grep` | the regex, not the search root | `grep` |
| `shell` | the raw command text | `bash` and `powershell` |
| `external_directory` | one resolved path outside the workspace | all five file tools |

A tool name maps to a key in `agent.KEYS`: `write` → `edit`, `bash` and
`powershell` → `shell`. A name that is not in `KEYS` is not gated here; an
unknown name is already answered with `Unknown tool:`.

### The matcher

`*` matches any run of characters, including `/` and a newline. `?` matches one
character. Everything else is literal, and the match is anchored (`fullmatch`).
`pathlib.Path.match` is not used: there `*` stops at `/` and `**` is special.

On Windows both the pattern and the value have `\` turned into `/` and are
case-folded before matching. On Unix both are compared as written, so a rule is
case-sensitive there. The rule table is always normalized the same way as the
value, so a rule written with `\` cannot miss.

### `ask`

`permissions.ask["fn"]` is `None` in `agent.py` and set by `__main__.py` at
import. The loop never imports the REPL; the REPL registers a callback. With no
callback, `ask` resolves to `deny`.

The prompt:

```text
Permission: {key} | {value}
[o]nce / [a]lways / [d]eny:
```

| Answer | Effect |
|---|---|
| `o` or `once` | run this one call |
| `a` or `always` | run it and remember this exact `(key, normalized value)` for the session |
| anything else, empty, EOF, Ctrl+C | `deny` |

`ALWAYS` holds normalized pairs, not patterns. `git status` does not cover
`git status --short`, and one approved path does not cover the next. It is
saved in the session file as `always` and restored on resume; `/new` and
deleting the active session clear it. A rule that resolves to `deny` is checked
before `ALWAYS`, so a remembered approval cannot lift a deny rule.

### Denials

```text
Permission denied: {key} {value}
Permission denied: read {resolved path}
Permission denied: external_directory {resolved path}
```

`{value}` is the string the model sent, for `edit`, `glob`, `grep`, and
`shell`. The two path cases print the resolved path in forward-slash form,
because the model sent a relative one. A denial is appended as `role: "tool"`
and printed through `_tool_note`: no `|Tool Used:` line.

### Order of checks

`agent.agent` runs, per tool call:

1. plan deny (`PLAN_DENIED`) — `docs/modes.md`;
2. registered? otherwise `Unknown tool: {name}`;
3. `_permit` — the gate below;
4. the tool, inside a `try`/`finally` that clears the one-shot approvals.

`_permit` itself, in order:

1. parse the arguments as JSON; malformed or non-object returns `None` and the
   registry reports `Invalid Arguments:` instead of prompting;
2. if a `path` string is present on a file tool, classify it
   (`docs/workspace.md`). A `.env` path asks under key `read`; an outside path
   asks under `external_directory` and, on allow, approves that exact `Path`;
3. map the tool name to a key, extract the value, and call `decide`;
4. in plan mode, a shell command that `plan_touches` returns true for goes
   through `force_ask` instead, which prompts even when the rule says `allow`.

`force_ask` still honours a `deny` rule and an `always` pair. It differs from
`decide` only in ignoring an `allow` rule.

`resolve_path.approve` stores the `Path` that `classify` resolved. `_resolve`
accepts that exact path once the gate has allowed it, and the loop calls
`clear_approved()` in a `finally`, so an approval never outlives its call. A
boolean "outside is fine" flag would let a later `glob` or `grep` walk past the
one path the user agreed to.

### Plan mode and the shell

`PLAN_DENIED` keeps `write` and `edit` out of the schema, so plan asks nothing
for them: they are not offered at all. The shell stays in the list and is
gated by command text.

`plan_touches(command)` is true when the command contains `>` or when a
pipeline segment's first word, lowercased and stripped of any path, is one of:

```text
rm rmdir del erase touch mkdir mv cp ln cat head tail less more
```

Segments are split on `&&`, `;`, and `|`. `ls`, `pwd`, `git`, `python`, `echo`,
and `find` do not ask. Nothing past the first word is parsed.

A denied plan shell prompt returns one sentence, not the command:

```text
Plan mode: that command was denied. Do not try another shell command to create or change a file. Tell the user to run /build.
```

The prompt itself still showed the command.

## Why this shape

**OpenCode's model, minus the scanner.** OpenCode documents `allow` / `ask` /
`deny` with last-match-wins and a separate `external_directory` gate. That part
is copied. Its command scanner is not: a scanner is a parser that must be
right about every shell's quoting, and a wrong parse is a silent allow.

**In-workspace edits are silent.** Pi's argument, and OpenCode's current
default: once the workspace bounds the path, prompting on every `write` is
theater. The prompt that matters is the one for a path outside the workspace,
and for a `.env`.

**Shell is `allow`, with `.env` text as the exception.** An approval prompt on
every command would be noise in a coding session; the workspace already bounds
`cwd`, and `external_directory` bounds paths the file tools take. The one thing
that is never routine is reading a secret, so `*.env*` asks.

**Plan asks on content-read, create, and delete verbs.** Plan is for reading
and reasoning, so the commands that change state ask even though the shell rule
allows them. First-word matching is cheap and honest about its limits: it
catches `rm`, `touch`, `cat`, and a redirect, and it does not pretend to catch
`python -c` writing a file.

**The prompt is a callback.** `agent` imports `permissions`, but `permissions`
must not import `__main__`. A dictionary slot that `__main__` fills keeps the
dependency pointing one way, and a missing slot fails closed.

**Approvals are exact.** A pattern approval (`.env*`, `docs/**`) is how a
permission system becomes a blanket allow. Exact pairs bound `always` to the
string the user just saw.

## Invariants

- Last match wins; no match denies. `permissions.check`.
- `ALWAYS` is consulted only after the rule resolves to `ask`, except in
  `force_ask`, which also consults it before prompting. A `deny` rule wins in
  both. `permissions.check`, `permissions.force_ask`.
- A missing prompt callback denies. `permissions.decide`.
- `approve` takes a resolved `Path`, never a string, and the loop clears it in a
  `finally`. `agent.agent`.
- `.env` is classified before the external check, so an outside `.env` asks
  under `read`, not `external_directory`.
- A gate denial appends a tool message and prints no `|Tool Used:` line.
- A plan-denied tool never reaches `_permit`; a plan-denied shell command does,
  and gets the short sentence.

## Edge cases

| Input | Result |
|---|---|
| `read` of `notes.txt` | allow, no prompt |
| `read` of `.env` or `.env.local` | `ask` under key `read`, resolved path shown |
| `read` of `.env.example` | allow |
| `write` of `.env` | asks, and the prompt says `read`, because `.env` is one classification |
| `.env` on Unix as `.ENV` | allow, because Unix matching is case-sensitive |
| `shell` `cat .env` | `ask` |
| `shell` `echo $env:FOO` | allow; no `.env` substring |
| outside path, answered `once` | runs; the next outside path asks again |
| outside path, answered `deny` | `Permission denied: external_directory {path}` |
| malformed arguments | `Invalid Arguments:` from the registry, no prompt |
| `always` on a command, then the same command in plan | allowed without a prompt |
| plan, `touch x` and the user denies | the short `/build` sentence, no shell block |
| plan, `ls > out.txt` | asks, because of `>` |

## Verification

- `write` a file inside the workspace: no prompt, one `|Tool Used:` line.
- `read` a path outside the workspace: `Permission: external_directory | ...`
  with the resolved path; `o` runs it, `d` returns the denial.
- `read .env`: prompt under `read`; denying leaves the file unread.
- `read .env.example`: no prompt.
- In plan, `cat README.md` asks; `git status` does not.
- `always` on `git status`, then `git status --short`: the second still asks.
- Resume a session: a previously remembered command does not ask. `/new`, then
  the same command: it asks again.
- A guessed `write` in plan is refused before any prompt appears.

## Gaps

- No config file. The default table is the policy; changing it is a code change.
- No prefix allows, no argument-level rules, no per-directory rules.
- The shell is gated on command text, so `python -c "open(...).write(...)"` is
  allowed outside plan and asks inside plan only if a touching verb or `>`
  appears.
- The child process inherits the environment; `$env:GEMINI_API_KEY` is not a
  permission event.
- `always` is session-scoped. There is no durable per-project approval list.
- A `deny` row exists in the engine but not in the default table, so there is
  no way to express "read this checkout, do not edit it" yet.
- Writing a `.env` asks under the key `read`, which reads oddly in the prompt.

## History

- 2026-10-23  The gate arrived: `allow` / `ask` / `deny`, last match wins,
  `external_directory` as its own key, exact `always` pairs, and shell as
  `ask`.
- 2026-10-25  `.env` stopped being a hard refusal and became an `ask`; shell
  became `allow` with `*.env*` as the exception; plan-mode verb matching
  arrived with `plan_touches` and `force_ask`.
- 2026-10-29  `always` became durable: saved in the session file, restored on
  resume, cleared by `/new` and active delete.
