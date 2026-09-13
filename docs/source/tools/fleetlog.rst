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

Every received message is stamped with its sender in the transcript, and every
``SendMessage`` call is recorded with its recipient, so the graph is derived, not
logged. A message appears in both the sender's and the receiver's transcripts; the
duplicate is dropped.

Old names are mapped onto current sessions without a hand-kept table: a transcript's
earlier self-reported names map to its latest name if that is a current session,
otherwise to the current owner of its working directory (from the last snapshot).

``verify`` is proof of possession: a transcript that contains the text you sent to a
session belongs to whoever receives at that address. Your own transcript, which
necessarily contains what you sent, is marked and not counted.
