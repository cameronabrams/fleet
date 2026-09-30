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

The **bill** is not an estimate. Every assistant turn records `message.usage`, so the
tokens actually read — input, cache reads and cache writes — are read straight off the
transcripts. Most of them are cache reads, billed at a fraction of the input rate, so
the figure is a token count and not a price.

**Survival is a model**, and the model is compaction: a message is re-read on every
assistant turn until the context holding it is compacted, which is what actually
evicts it. A ``/clear`` needs no special case — it starts a new transcript, so the
file simply ends.

.. note::

   Until 2026-09-30 both numbers came from a fixed 200k-token window applied as a
   sliding byte cap. One stale constant produced two wrong figures: the bill was
   truncated at the cap — 88% of turns exceeded it, so the reported total was about
   half of what the transcripts said had been read, while the output labelled itself
   an *over*-count — and survival was cut off at the same boundary, putting
   amplification at roughly a third of what the compaction records show. A sliding
   byte window was never the mechanism: compaction summarizes rather than slides.

It scans every project directory. Narrowing the scan to save time once hid a whole
session's traffic.
