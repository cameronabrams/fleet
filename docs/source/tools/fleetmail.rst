fleetmail
=========

.. tooldoc:: fleetmail

Usage
-----

.. code-block:: text

   fleetmail send TO "TEXT" --as SESSION [--kind K] [--thread T] [--attach FILE] [--go]
   fleetmail fetch [--go] [--nudge-wait SECONDS]
   fleetmail inbox
   fleetmail ack ID [TEXT] --as SESSION [--go]

Every other channel this fleet has stops at one machine: ``SendMessage`` needs a unix
socket and one uid, drops are files in one state directory, and :doc:`fleetnudge` types
into a pane it can see. ``fleetmail`` carries the same protocol — a pointer and a
one-line conclusion, never a payload — between fleets owned by different people.

The mailbox
-----------

A git repository, declared as ``[mail]`` in :doc:`../configuration`:

.. code-block:: text

   mail/<fleet>/<stamp>-<from-fleet>-<from-session>-<slug>.md   one message
   mail/<fleet>/attach/<stamp>-<name>                           an attached file
   mail/<fleet>/INBOX.md                                        what a human reads
   fleets.toml                                                  who may correspond

Git rather than something lighter: the author of a message is a claim someone can
check, a committed message survives a ``/clear`` where a socket message evaporates,
nothing here listens on a port, and access is granted and revoked in one place.

A message is front matter and a short body:

.. code-block:: text

   ---
   from: north/literature
   to: south/coord
   thread: 2026-09-18-pet-cutinase
   kind: question
   ---
   One line: the conclusion, and where the detail is.

Addresses are ``<fleet>/<session>`` because two fleets both have a ``coord``. That
namespacing exists **in the mailbox only**. Delivery resolves a session by its bare
name, machine-wide, so two fleets sharing a workstation must not share a session name:
a loopback test on 2026-09-18 delivered its test mail into the live ``coord``.

Trust
-----

A foreign fleet is not your human, so these are enforced, not conventional:

- ``kind`` is ``question``, ``report`` or ``ack``. Anything else is refused.
- **The body may not claim authority or consent**, whatever ``kind`` says. ``kind`` alone
  is not enough: an ``ack`` reads as consent already given, which is the laundering
  shape. The wording guard covers verbs like authorize, approve, charge, publish,
  delete, "you may", "do it for me", and the mailbox can name more in
  ``fleets.toml``:

  .. code-block:: toml

     [guard]
     refuse = ["grant-a", "grant-b"]      # e.g. billing accounts

  Refused at send time, and quarantined on delivery if it arrives anyway. Such a
  thing can still be *reported* in an ``--attach`` file, which a human reads.
- Correspondents are declared in the mailbox's ``fleets.toml``. Mail to or from an
  unlisted fleet is refused; inbound mail from one is quarantined: kept, reported,
  never delivered.
- **Mail lands as a FILE**, never as keystrokes from a remote party. Each message is
  written into this fleet's drops directory with a header saying it is data from
  another fleet, carries no authority, and that a request to do something refused
  elsewhere goes to the local human. Only then does :doc:`fleetnudge` type one line,
  naming the sender: ``[mail: south/coord -> you] <first line>; read drops/<file>``.

Delivery
--------

``fetch`` pulls, then for each message addressed to this fleet that the state directory
has not recorded: validates it, writes the drop, nudges the session, records the path,
and rebuilds ``INBOX.md``. Keying on the path makes it idempotent — running it twice
delivers once.

``INBOX.md`` carries a **delivery** column, because a message that reached the machine
but never reached its session must be visible where a human looks, not only in a log.
``fleetmail inbox`` prints it plus anything quarantined or undelivered.

**A mailbox that cannot be read is never "no mail".** A failed pull says so and exits 4.

Exit codes
----------

.. list-table::
   :widths: 10 90

   * - ``0``
     - fine, or a plan with no blocks
   * - ``2``
     - refused: the address, the kind, the guard, or an unknown fleet
   * - ``4``
     - the mailbox could not be reached
   * - ``5``
     - delivered as files, but at least one session could not be told
