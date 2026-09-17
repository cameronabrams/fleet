---
name: waiting
description: Report which agent sessions are blocked waiting on the human for a decision, and what each is asking. Use when the human asks who needs them, what is waiting on them, what is blocked, whether anyone needs a decision, what they owe the fleet, or for a queue of pending asks across sessions. Triggers on "who's waiting", "what needs me", "am I blocking anything", "what's pending on me", "anyone need a decision".
---

# Who is waiting on the human

"The human" is the person the fleet works for: `[human] name` in `fleet.toml`, and
whatever `[human] aliases` sessions use for them.

Answer with a short, ranked queue of decisions the human actually has to make. Not a
status report — they can ask for one of those separately.

## Gather three sources, in this order

**1. `ListAgents` — live and authoritative on state.** A session reported as
`waiting` is blocked *now*, whatever any transcript says. Note also `busy` and
`shell`: a session mid-work is not waiting on the human even if it said so an hour ago.
Watch for two sessions sharing a name — forks and renames both cause it, and an
ambiguous name means you cannot safely attribute a request to one of them.

**2. `fleetwaiting`** — scans each live session's own output and its own outbound
messages for statements that it is blocked on the human, then checks whether anything
after it reads like a resolution.

**3. The standing board**, if one is published — it carries decisions already
recorded as open, with their consequences.

## Reconcile, do not concatenate

`fleetwaiting` **over-reports**: a resolved item whose resolution used unusual
wording still shows, and "I'll put it to them" is an intention rather than a
pending ask. It **under-reports**: a session blocked without ever saying so does
not appear at all, and it cannot see a question asked only in that session's own
pane. Treat it as a prompt to check, in the same way an orphan-process notice
tells you what is not running rather than what was lost.

Where the sources disagree, or where an item is consequential and its status is
unclear, **ask the session** rather than guessing. One message costs nothing;
telling the human something is settled when it is not is how a decision gets made
twice or never.

## Report

Rank by **what unblocks the most work**, not by age. For each:

- which session, and how long it has been waiting
- **the decision, in one line** — what the human actually has to choose
- what it blocks, if anything, and what happens if nobody decides
- whether it is genuinely the human's: releases, pushes, publishing, deletions,
  allocation spend and external email always are; most other things are not

Separate clearly:

- **Needs a decision** — the human must choose
- **Needs only a word** — a yes that a session is holding for form
- **Reported waiting, looks resolved** — say why you think so, and do not
  silently drop it
- **Blocked on something other than the human** — a job, a peer, a tool

Quote a session's own words for anything consequential. A paraphrase of a request
can be accurate about its subject while losing the thing being asked.

## Do not

- Do not resolve anything on the human's behalf, and do not tell a session they
  decided something because it seems obvious.
- Do not treat a peer's account of what the human said as what they said.
- Do not pad the queue. If nothing needs the human, say so in one line — that is a
  useful answer and the most common correct one.
