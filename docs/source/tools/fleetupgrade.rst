fleetupgrade
============

.. tooldoc:: fleetupgrade

Usage
-----

.. code-block:: text

   fleetupgrade           table + ordered plan
   fleetupgrade --json    the same, machine-readable

Columns
-------

``SESSION``
   the session's own last ``agent-name`` record, else the pane title
``VERSION`` / ``STALE``
   the binary the process runs, against the installed ``~/.local/bin/claude``
``LEDGER``
   whether ``<state>/rearm/<name>.md`` exists — existence only, not truth
``COLOR``
   the live color; ``LOST`` when a transcript was read and has none, ``?`` when no
   transcript could be resolved
``RESUME UUID``
   the transcript ``--resume`` should reopen

Warnings follow for colors that differ from ``[colors]``, pane titles that disagree
with the session's name record, handles that could not be resolved (another claude
outside tmux shares the directory — the tool refuses to guess), and names taken only
from a pane title.

The plan lists stale sessions with their relaunch commands, coordinator last. The
session running the tool cannot restart itself, so it gets a separate block with the
two commands to type — ``/exit``, then ``cd <dir> && [env] claude --name <name>
--resume <uuid>``, using the session id from its own environment.

It restarts nothing. The :doc:`fleet-upgrade skill <../skills/fleet-upgrade>` drives
a roll.
