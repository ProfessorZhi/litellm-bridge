# DeepSeek Anthropic Messages: inline `tool_definition` is rejected by the provider

## Symptom

A client that surfaces a deferred tool mid-session can declare that tool **inline**, as a
`tool_definition` content block inside `messages[].content`, rather than listing it in the request's
top-level `tools[]`. The DeepSeek Anthropic-compatible Messages route has no `tool_definition`
content variant, so the request is refused at the wire-format layer:

```
messages[N].content: unknown variant `tool_definition`, expected `tool_reference`
```

The turn fails. Retrying the same conversation resends the same body and fails identically, so the
session is stranded.

On the pinned baseline the DeepSeek Messages transform forwards the client body unchanged — it does
not convert the block and does not refuse it locally, so an unparseable block reaches the provider.

## Fix

`llms/deepseek/messages/transformation.py` gains a downgrade step that runs **only** for the DeepSeek
Messages route:

* every inline `tool_definition` block is rewritten in place into a `tool_reference`, keeping message
  index, block index and block order;
* its declaration is hoisted into `tools[]` exactly once (repeats are deduped);
* the official mid-conversation form is supported too — in
  `{role: "system", content: [{type: "tool_addition", tool: {type: "tool_definition", ...}}]}` the
  outer `tool_addition` stays where it is and only its `tool` becomes a reference;
* anything that cannot be hoisted losslessly — no resolvable name, no usable `input_schema`, or a
  duplicate name with a conflicting schema — **fails closed** with a client error instead of being
  dropped or forwarded;
* a final guard refuses any `tool_definition` that survives in a **protocol block position** deeper in
  the tree (for example inside a `tool_result`'s nested `content[]`, or under a repeated
  `tool_addition` wrapper), naming the path;
* `tools[]` is validated as a **declaration container**: an entry whose own `type` is
  `tool_definition` / `tool_addition` is refused, because a content block is not a declaration. The
  check looks only at that discriminator — it never walks a tool's `input_schema`, so a schema
  property or description that merely contains the text `tool_definition` is left alone.

The guard walks **only** the positions where the provider expects a content block
(`messages[].content[]`, a `tool_result`'s nested `content[]`, a `tool_addition`'s `tool`). It does not
descend into `tool_use.input` or any other user JSON: a `"type": "tool_definition"` pair there is data
the provider never parses as a block, so rejecting it would be a false positive. Keeping the walk
protocol-scoped also keeps the common no-inline request cheap — on a synthetic 50-message / ~1.3 MB
body the guard went from ~15.6 ms to ~0.18 ms (≈84×) with an identical verdict.

Legal traffic is untouched: with no inline definition the request takes an early return and is
byte-identical to baseline.

## Tests

`pytest tests/test_litellm/llms/deepseek/` — 80 passed, covering the conversion, the two accepted
block shapes, the official `tool_addition` form, dedupe/conflict handling, the fail-closed paths, the
deep-nesting guard, and streaming/non-streaming equivalence.

## Limitations

* The conversion is verified against hand-built requests and a strict mock. The originating report has
  **not** been reproduced end-to-end from a real client: a real client driven through the same chain
  used the provider successfully but never emitted an inline block, so the trigger was not observed.
  Treat this as a fix for a shape the transform must handle, not as a confirmed production fix.
* Deeper nesting is refused rather than converted — an accepted degradation, not full protocol parity.
* Duplicate declarations with different schemas are refused rather than guessed at.
* The **flat** inline shape (`{type: "tool_definition", name, input_schema}` with no `definition`
  wrapper) is supported and unit-tested but has **not** been observed on the live provider; treat it as
  **experimental**, unlike the nested `definition` shape.
* Nothing is deployed.
