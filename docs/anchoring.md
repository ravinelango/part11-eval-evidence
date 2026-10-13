# Anchoring the chain head

`run_log.jsonl` is hash-chained: every entry commits to the one before it, so editing,
reordering, or deleting an entry in the middle breaks `p11e verify`.

That check has a known gap. Someone who can rewrite the whole file can rebuild a fresh,
internally consistent chain, and they can also drop entries from the end. In both cases
`p11e verify` alone still passes. The fix is to record the final hash (the **chain head**)
somewhere the person running the eval can't quietly change, and compare against it later.

## 1. Record the head right after the run

```bash
p11e build ... --out out
p11e head out/run_log.jsonl
```

`p11e head` prints one 64-character SHA-256 value. The same value is in
`out/manifest.json` under `meta.chain_head`, but the manifest lives next to the log, so it
doesn't count as an independent record.

Store the head outside the evidence folder, ideally in a system with its own audit trail
and access control. Options, roughly from strongest to weakest:

| Where | Notes |
|---|---|
| QMS / validation record (e.g. the change or test record for this run) | Best fit for GxP work: already access-controlled and audited |
| Ticket in your issue tracker | Comment history gives a timestamp and an author |
| Signed git tag or commit in a separate repo | `git tag -s` with a message containing the head |
| Email to a QA mailbox | Weak, but better than nothing |

Write down the run ID and the date next to the head so the record can be matched to the
package later.

## 2. Check against the recorded head

```bash
p11e verify out/run_log.jsonl --expect-head <recorded-sha256>
```

Exit code `0` means the chain is intact **and** its head matches the recorded value.
Exit code `1` lists every problem found, including a head mismatch.

## What this does and doesn't give you

- It turns "the log is self-consistent" into "the log is the same one that existed when
  the head was recorded". That supports 11.10(a) (discerning altered records) and
  11.10(e) (audit trails) more convincingly.
- It is only as trustworthy as the place the head is stored. The tool does not sign
  anything and does not talk to any external system.
- Recording the head is a manual step. Put it in your procedure (SOP or test script) so
  it isn't skipped.
