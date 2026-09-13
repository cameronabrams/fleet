fleetcost
=========

.. tooldoc:: fleetcost

Usage
-----

.. code-block:: text

   fleetcost             summary
   fleetcost --senders   per-sender volume
   fleetcost --worst     the most expensive individual messages

For every cross-session message in every transcript over 10 kB, it counts the
assistant turns the message then sits through in the receiver's context, capped at a
~200k-token window. Cost is size times turns. The headline number is the
**amplification**: tokens re-read per token written.

It scans every project directory. Narrowing the scan to save time once hid a whole
session's traffic.
