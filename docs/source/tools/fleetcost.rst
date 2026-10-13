fleetcost
=========

.. tooldoc:: fleetcost

Usage
-----

.. code-block:: text

   fleetcost             summary
   fleetcost --senders   per-sender volume
   fleetcost --worst     the most expensive individual messages

Transcripts are deduplicated by session before anything is summed
(``fleet.transcripts.dedupe_paths``). A renamed working directory leaves one
session's transcript in two project directories, and summing per *file* counted
three sessions twice until 2026-10-08: 101 transcripts where there were 98, and
2,528 peer messages where there were 2,353. The amplification ratio barely moved
(367x to 365x) because its two sums inflate together; **the counts are the fragile
figures here, not the ratio.** Figures measured before 2026-10-02 predate the
duplicates and are unaffected.

For every cross-session message in every transcript over 10 kB, it counts the
assistant turns the message then sits through in the receiver's context until that
context is compacted. Cost is size times turns. The headline number is the
**amplification**: tokens re-read per token written.

The **bill** is not an estimate. Every assistant turn records `message.usage`, so the
tokens actually read — input, cache reads and cache writes — are read straight off the
transcripts. Most of them are cache reads, billed at a fraction of the input rate, so
the figure is a token count and not a price.

**Survival is a model**, and the model is compaction: a message is re-read on every
assistant turn until the context holding it is compacted, which is what actually
evicts it. A ``/clear`` needs no special case — it starts a new transcript, so the
file simply ends.

The record is not the message
-----------------------------

What an arrival costs is the whole **record**, and the record is larger than the
message by a near-constant 723 characters. Every arrival carries an envelope the
receiver re-reads exactly like the body: a line of prose, the
``<cross-session-message ...>`` tag naming the sender's socket, name and mode, the
close tag, and a paragraph of handling advice after it — 543 of the 723 is that
trailing paragraph alone. It is measured on each run rather than assumed, because
the tag varies with the sender's name and the prose around it belongs to the
harness, not to this repository.

The sums always included it. The two printed **examples** did not, until
2026-10-13: they read the character count the reader supplies as the size of the
whole record, so a message written to the 800-character convention was quoted at
~55,600 tokens where it costs ~106,000. Understated 1.9x at 800 characters and
1.2x at 4,000. The examples now name the **body**, which is the thing the
convention governs and the only part a session controls.

**Amplification did not move**, and that is not luck. The envelope is in both of
its sums and divides out — the same reason the ratio survived the duplicate
transcripts while every count shifted. Figures quoted for amplification stand;
figures quoted from the two example lines before 2026-10-13 are low.

Compliance with the 800-character rule is reported as the share that **obeys**,
measured on the **body**. Both halves of that are load-bearing. Measured on the
record the answer is 0% and always will be, since the envelope alone exceeds the
ceiling: a rule about what a session writes, scored against something it does not
write. And the share that breaks the rule, printed under the name compliance,
reads as a convention working when it is the same number saying it is not — on
this fleet 45% of bodies obey it, so the inverted reading would report 55%.

The envelope is **36% of the whole re-read bill**, which is a floor that no
convention about what sessions write to each other can reach. Capping every body
at 800 characters would bring the bill to 72% of what it is: the rule's ceiling is
a 28% saving.

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
