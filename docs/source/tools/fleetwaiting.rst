fleetwaiting
============

.. tooldoc:: fleetwaiting

For each labelled pane, it finds the session's transcript — preferring one that
self-reports the pane's label — and scans the last 2.5 MB of it. Only the
session's own words count: its assistant text and the messages it sent with
``SendMessage``. Messages sent *to* it are ignored, so a sender's blocking language
is never reported as the receiver's.

It reports the last sentence matching a "blocked on the human" pattern, how old it
is, and whether anything after it reads as a resolution. The session running the
tool is skipped.

The patterns are built from ``[human]`` (:doc:`../configuration`).

Treat the output as a prompt to check. ``ListAgents``' ``waiting`` state is live and
authoritative in a way transcript text is not.
