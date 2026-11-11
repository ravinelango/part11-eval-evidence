# promptfoo export from a real offline run (echo provider)

Unlike `examples/promptfoo_synthetic/` (hand-written rows), `results.json` here is
the unedited file written by a real `promptfoo eval -o results.json` run
(promptfoo 0.125.1), so it pins the adapter to the export shape promptfoo
actually produces.

**The questions are synthetic and the provider is promptfoo's built-in `echo`,
which returns the rendered prompt without calling any API.** The 1-of-3 pass
rate only reflects whether the synthetic question text happens to contain the
asserted string; it says nothing about any real model.

To regenerate (the eval id and timestamps will differ):

```bash
npx promptfoo@0.125.1 eval -c examples/promptfoo_echo_run/promptfooconfig.yaml \
    -o examples/promptfoo_echo_run/results.json --no-cache
```

Tests carry `metadata.test_id` / `metadata.requirement_id`, so they map to
`examples/synthetic_run/requirements.yaml`:

```bash
p11e build --format promptfoo --results examples/promptfoo_echo_run/results.json \
           --requirements examples/synthetic_run/requirements.yaml --out out-pf-echo
```

Expected: 3 tests, PF-ECHO-1 passes and PF-ECHO-2 fails (REQ-001), PF-ECHO-3
fails (REQ-004), and REQ-002 / REQ-003 are reported NOT TESTED.

Note: a real export fills `error` with the assertion message on an ordinary
failure (`failureReason: 1`). Only `failureReason: 2` is a provider/runtime
error, and the adapter now maps it that way.
