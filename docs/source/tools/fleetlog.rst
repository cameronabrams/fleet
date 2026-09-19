fleetlog
========

.. tooldoc:: fleetlog

Usage
-----

.. code-block:: text

   fleetlog [--all]              who talked to whom (current sessions, last 14 days)
   fleetlog timeline [-n 40]     chronological traffic
   fleetlog trace <keyword>      every message mentioning <keyword>
   fleetlog sessions             transcript -> identity, and how it was resolved
   fleetlog verify <session> [-n 3]
                                 do my recent messages to <session> appear in the
                                 transcript it claims?
   fleetlog initiative [--since YYYY-MM-DD] [--json]
                                 what triggered each message sent

Every received message is stamped with its sender in the transcript, and every
``SendMessage`` call is recorded with its recipient, so the graph is derived, not
logged. A message appears in both the sender's and the receiver's transcripts; the
duplicate is dropped.

Old names are mapped onto current sessions without a hand-kept table: a transcript's
earlier self-reported names map to its latest name if that is a current session,
otherwise to the current owner of its working directory (from the last snapshot).

Who starts a conversation
-------------------------

``initiative`` labels every message by what triggered the turn it was sent in, which
the transcript records: ``instructed`` (the human's words named the recipient),
``volunteered`` (the human was talking about something else), ``reply`` (a peer wrote
and the session answered that peer), ``onward`` (a peer wrote and the session told a
different one — routing it chose), and ``auto`` (a watcher, a notification or another
system event). ``volunteered + onward`` is the fleet talking to itself.

It prints the mix, a row per session, and a week-by-week trend with the median message
length and the share over the fleet's own 800-character ceiling.

Only ``instructed`` is a heuristic — it fires when the recipient's name, or a name that
session used to answer to, appears in the human's words. It undercounts "tell the
others" and overcounts a prompt that mentions a session for an unrelated reason, so the
output says so. The other four are mechanical.

Three record shapes each produced a confident wrong answer before they were handled,
and every one of them looked plausible:

- A tool **result** is stored as a ``user`` record. Counting one as a turn resets the
  trigger at every tool call and put 93% of sends down to a system event.
- An incoming peer message is a ``user`` record with ``isMeta``. Filtering meta records
  out scored peer-triggered sends at exactly zero.
- One incoming message is written **three times** — an ``attachment`` record, a
  ``queue-operation``, then the ``user`` record that actually starts the turn. Dropping
  the repeats, which is right for the graph, leaves the turn looking human-triggered:
  replies read as 1% of traffic instead of 39%.

``verify`` is proof of possession: a transcript that contains the text you sent to a
session belongs to whoever receives at that address. Your own transcript, which
necessarily contains what you sent, is marked and not counted.
