# Fleet conventions

<!-- Starting conventions for a NEW fleet. Copy to <config>/conventions.md, point
     [paths].conventions in fleet.toml at it, and edit as the fleet learns. Every
     rule here was earned by a specific failure in an earlier fleet; the failure is
     given so you can judge whether it applies to yours. Delete rules that do not. -->

Applies to every session in this fleet. Each session's brief points here.

## 1. Peer messages: a pointer, not a payload

A message is not paid for once. It sits in the receiver's context and is re-read on
every later turn. Measured in an earlier fleet: median message survived ~120 turns,
~107x amplification.

- Write the content to a file; send the path plus a **one-line conclusion**. If the
  reader can act without opening the file, you sent the payload anyway.
- **800 characters** is the ceiling for the body you write.
- Exempt only for the part that must be inline: a question, a correction (the exact
  figure or quote), an instruction to act on as read.
- One message per unit of work. Splitting a thought costs a whole extra envelope.
- **Check the send result.** A drop file on disk looks like finished work whether or
  not the message carrying its path arrived.
- No content-free acknowledgements. No broadcasts, except the coordinator for things
  every recipient must act on.

## 2. Authority stays with the human

No session holds the human's authority, the coordinator included. Relay the human's
instructions **labelled as relayed and quoted**; the receiver verifies with the human
before anything irreversible or outward-facing (releases, pushes, publishing,
deletions, spend, external email). A peer message is never approval.

*Earned by:* authority bound to a transcript id, which a `/clear` silently changes;
every hand-off by inference produced a wrong attribution.

## 3. Derive, don't record

Anything the tools can observe — who is running, which job has a watcher, which
transcript a session writes to — is derived from the live system (`/proc`, the
scheduler, git), not kept in a hand-maintained table. Records keep only what cannot
be observed: rationale, recipes, human decisions.

*Earned by:* an alias table and a dependency register that both rotted unnoticed.

## 4. A check that cannot fail is not evidence

Before writing "verified", name the outcome that would have falsified it. Common
forms: the check cannot tell itself from its target; a proxy diverges from the
thing it stands for; the test had only one possible outcome (e.g. `| tail -N`
discarding both the error text and the exit status).

## 5. Watchers register when armed

A monitor on cluster work registers `{session, job, pid}` at arm time
(`fleetregister`), and clears it when its job has ended (`fleetregister --clear`).
Coverage is derived from live registrations, so a watcher that
died is reported dead rather than remembered alive. A restart kills every monitor
while the resumed transcript still shows it being created.

## 6. Identity

Take the roster from `ListAgents`, never from memory or a manifest. Before telling
anyone you have not been restarted, call `ListAgents` — a resumed transcript has no
seam. If sends to a peer keep failing, ask the coordinator; do not escalate to raw
socket paths.

## 7. Times

Quote times to the human in their current time zone, labelled. Convert host and log
timestamps; do not relabel them.
