---
name: fleet-bootstrap
description: Stand up a fleet of long-lived Claude Code sessions from a coordinator, or add or retire one session in an existing fleet - designing roles, writing each session's brief, creating the tmux pane, launching it, verifying it, and snapshotting. Use when asked to start a new fleet, to be a fleet coordinator for a set of repos or projects, to spin up / add / onboard a new agent or session, to give a project its own agent, or to retire a session. Triggers on "new fleet", "bootstrap a fleet", "you are the coordinator", "spin up an agent", "add a session", "new agent for", "create a pane for", "fleetspawn", "retire a session", "shut down that agent".
---

# Bootstrapping a fleet, one session at a time

A fleet is a set of long-lived Claude Code sessions, each pinned to one directory
and one role, plus a coordinator that owns no directory and routes between them.
Adding a session looks like typing `claude` in a new pane. It isn't: the session
needs a role it can re-read after a restart, a place in the recovery snapshot, and
a name that nothing else answers to. Each of those, done by inference instead of by
a record, has failed at least once.

**The mechanical part is `fleetspawn`. The judgement is here and with the human.**

## 0. Which case is this?

| case | go to |
| :--- | :--- |
| No fleet exists; you have been asked to coordinate one | §1, then §2 for each session |
| A fleet exists; one more session is needed | §2 |
| A session's work is finished | §4 |

Before any of them, run `ListAgents`. The roster is what it says, not what a
manifest, a checkpoint or your memory says.

## 1. Founding a fleet

### 1a. Prerequisites — check, do not assume

- tmux server running; the human is attached to it.
- The fleet application installed (`<app>/install` shows the plan, `--go` applies).
- `<config>/fleet.toml` exists, from `examples/fleet.example.toml`.
- `<config>/conventions.md` exists, from `examples/conventions.example.md`, and
  `[paths].conventions` points at it. **A new fleet does not inherit the lessons of
  an old one unless this file carries them.** Read it with the human and delete
  rules that do not apply rather than shipping them unread.
- You are the coordinator, and the human launched you in a pane labelled for it
  (`tmux set -p @repo coord; tmux set -p @fleet coord`). You cannot spawn yourself.
- **The coordinator's working directory is the fleet STATE directory**, with the
  application and configuration as added directories
  (`permissions.additionalDirectories` in `<state>/.claude/settings.json`) and a
  short `<state>/CLAUDE.md` pointing at its brief. Not `~`: a home-directory project
  puts the whole home tree under the coordinator's trust, and shares its transcript
  and memory folders with every unrelated session started there (one such session
  was once reported as the coordinator). Not the application repo: that makes the
  coordinator a repo session and puts personal notes in shareable code. Not the
  configuration: that holds the human's declarations, which the coordinator edits
  as a delegate, deliberately. OBSERVED 2026-09-13: `--resume` from a different
  directory restores context but keeps writing to the ORIGINAL project folder, so
  move a coordinator with a fresh start, not a resume.

### 1b. Interview the human, then propose a roster

Ask, in one batch:

1. Which projects, and **which directory** is each in?
2. For each: is there production work — studies, sweeps, cluster campaigns — as well
   as code? Where does it run, and in which directory?
3. What writing is in flight (papers, talks, docs), and where?
3a. What shared resources should sessions consult or report into — a literature
   database, a lab notebook, a website — and who may write to each?
4. Which projects depend on which (whose bugs surface in whose runs)?
5. What must always come to the human: releases, pushes, spend, external email?
6. The human's time zone, and where that is recorded.

Then **propose a roster table** — name, kind, directory, fleet group, pane — and get
explicit approval before spawning anything. Adding a pane changes the human's screen.

### 1c. Role design — the part no tool can do

- **One directory, one role.** Two roles in one directory share a transcript
  directory, so every "newest transcript here" inference can pick the wrong one.
  If it is unavoidable, give them clearly different names and expect to verify
  identity by argv, never by mtime.
- **Split repo from production.** A *repo* session edits code; a *production*
  session runs released code at scale and reports what breaks back to the repo
  session. Production runs surface bugs that tests do not, and a session that both
  runs and patches will quietly patch around them. One-session-per-repo is the
  obvious design and it misses this; **ask** whether production exists (§1b.2).
- **Service sessions own a shared resource.** Some work is neither code nor a
  campaign: a database the fleet queries, a website or notebook that records results
  other sessions send. Its session is a *service*: it answers and records for the
  fleet, and it is the only writer of that resource. It may also maintain the tool
  behind the resource while that stays small. Write the **split triggers** into its
  brief: split into a service session plus a repo session when code work crowds out
  serving, when someone else starts running the tool, when a change would alter a
  contract other sessions depend on (an identifier scheme, a file format), or when a
  second instance of the resource appears. On a split the service keeps the live
  resource; the repo session tests against a scratch copy and never touches the live one.
- **The coordinator owns nothing.** No repo, no campaign. It routes, measures, rolls
  upgrades, keeps snapshots and holds conventions. The moment it owns work, its
  routing is no longer neutral and nobody is watching the fleet.
- **Idle is fine.** A repo session with nothing to do costs nothing. Do not merge
  roles to "use" idle sessions — merging pours one role's context into another's,
  and every turn re-reads it.
- **Authority stays with the human.** Do not design any session, yourself included,
  as holding it. Relay, quoted and labelled.

### 1d. Order of spawning

Coordinator (already running) → repo and service sessions → production sessions
(their briefs name the repo session they report to, which must exist) → writing
sessions. At most
four panes per window; group a project's sessions in one window. Do one at a time
through §2 — a batch launch that fails halfway is harder to reason about than four
single ones.

## 2. Adding one session

### 2a. Decide, with the human

Name (short, kebab-case, unique in `ListAgents`), kind, directory, fleet group, and
placement: `--beside <pane>` (split; `v` below, `h` right) or `--window <title>`.

### 2b. Prepare the directory

If it does not exist, confirm with the human, create it, and `git init` if it will
be a repo. Put **repo-specific** working notes in its `CLAUDE.md`. If the repo is or
may become public, keep personal paths, cluster accounts and fleet mechanics out of
it — those belong in the brief.

### 2c. Write the brief — required

`<config>/briefs/<name>.md`, from `examples/brief.example.md`. Role, kind, territory,
peers, conventions pointer, deadlines, first step. **Commit it in the config repo.**

Why configuration and not a drop directory: a brief is *declared*, it must survive a
disk loss, and it is what the session re-reads after every restart. On 2026-09-12 a
brief went into a scratch drop directory first, alongside messages that are meant to
be disposable.

Pointing the session at large files: tell it to read them **scoped** (grep headings,
read sections), and give paths, not pasted content.

### 2d. Declare ownership, if it runs cluster work

Add its WorkDir fragment to `[owners]` in `fleet.toml`, **specific before general**
(first match wins). Without it, `fleetwatch` reports that session's jobs as
UNATTRIBUTED — correctly, since nothing declared them.

### 2e. Plan, show, then spawn

    fleetspawn <name> <dir> --fleet <group> --beside <pane>        # plan; changes nothing
    fleetspawn <name> <dir> --fleet <group> --beside <pane> --go

Preflight blocks on: missing directory, missing brief, no `[colors]` entry, no tmux, a live claude already
`--name`d this, a pane already labelled this. Do not work around a block; fix its
cause. `[spawn]` in `fleet.toml` may set `env` (e.g. a notification flag) and
`first_prompt`; the default prompt tells the session to read its brief.

Exit codes: `0` live · `2` blocked · `3` stopped at the trust prompt · `4` timed out.

### 2f. The folder-trust prompt is the human's

A new directory triggers Claude Code's "do you trust this folder?" prompt.
**Do not answer it — not with `send-keys`, not because you just created the folder
and know every file in it.** Trusting grants an agent read, edit and execute there;
the decision is the human's. `fleetspawn` stops with exit 3 and names the pane; tell
the human, wait, then run `fleetspawn --check <name> <dir>`.

OBSERVED 2026-09-12: the coordinator answered it for a new session, reasoning that it
had created the folder moments earlier. The reasoning was sound and the action still
was not its to take. Directories already trusted (including a session's own
scratchpad) show no prompt, so a test there cannot exercise this path.

### 2g. Verify — each check must be able to fail

1. `fleetspawn --check <name> <dir>` — exactly one process, right cwd, pane labelled.
   It reports WRONG DIRECTORY and duplicate names; it has been seen to.
2. `ListAgents` lists `<name>` once. Two rows with one name make it unaddressable by
   name — find and resolve the duplicate before anyone messages it.
3. The pane shows the session reading its brief, not an error or an idle prompt.

### 2h. Record it

- **Re-arm ledger:** create `<state>/rearm/<name>.md` saying "re-arm nothing; this
  session holds no runtime", verified by checking it has no child processes.
  `fleetupgrade` flags a session without one as `MISSING`, and a missing ledger
  cannot be told apart from a forgotten one.
- **Snapshot:** `fleetsnap`, then verify per the `fleet-snapshot` skill. A brand-new
  session resolves as `verified: transcript self-reports this name`.
- **Coordinator checkpoint:** add it to the roster there.
- **Tell only the peers it will work with**, by pointer: "`<name>` now owns X; brief
  at <path>". Not a fleet-wide broadcast.
- **Colour — required.** Declared in `[colors]` in `fleet.toml` before spawning
  (preflight blocks without it); applied by the human typing `/color <c>` in the pane
  once the session is idle — there is no launch flag, and keys sent into a working
  session can be corrupted. A `/clear` drops the live colour and keeps the name;
  `fleetsnap` and `fleetupgrade` flag the difference and print the command.
  Duplicates are allowed if the human chooses them.

## 3. After spawning: what changes for everyone else

- A new production session means a repo session gains a reporter; say so in the repo
  session's brief as well as the new one's.
- The next `fleetupgrade` roll and `fleetsnap` include it automatically — both derive
  the roster from live processes. Nothing else needs a hand-kept list updated, and if
  you find one that does, that list is the bug.

## 4. Retiring a session

1. Ask the session to write its state where it belongs (repo, notebook) and to say
   what runtime it holds. Verify: `fleetwatch` shows no jobs owned by it, and it has
   no child processes.
2. With the human's approval, `/exit` in the pane (or `kill <pid>` by number — never a
   pattern), then `tmux kill-pane -t <pane>`.
3. Remove its `[owners]` and `[colors]` rows; move its brief to `<config>/briefs/retired/`; archive
   its re-arm ledger. Commit the config repo.
4. `fleetsnap`, verify, update the coordinator checkpoint, tell its former peers.

## 5. Anti-patterns

| don't | because |
| :--- | :--- |
| spawn with no brief | the role gets reconstructed later from transcript — an inference |
| keep colours in a hand note in the state dir | it rotted: 3 members missing and one wrong within two weeks (2026-09-13) |
| answer the trust prompt | it is the human's grant, §2f |
| one session per repo without asking about production | misses the split that surfaces bugs |
| give the coordinator a repo | nobody is left watching the fleet |
| reuse an idle session for an unrelated role | its whole context is re-read every turn for nothing |
| two sessions in one directory by default | identity-by-transcript becomes ambiguous |
| broadcast the new roster as an essay | n recipients × every later turn; send a pointer to those affected |
| `/clear` a session to "make room" for a new role | rolls its transcript; spawn a new session instead |
