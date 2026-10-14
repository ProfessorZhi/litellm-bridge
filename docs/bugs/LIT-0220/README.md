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
* anything that cannot be hoisted losslessly — no resolvable name, no object `input_schema`, or a
  second declaration of a name that `tools[]` already declares differently — **fails closed** with a
  client error instead of being dropped or forwarded;
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

## Protocol contract

The transform holds to the following contract. Each row names the class of evidence behind it,
because they are not worth the same and this fix has already been wrong once by treating a shape as
settled when it was not.

* **documented** — Anthropic's published Messages schema, or the error string the provider itself
  returned.
* **binary** — a static trace of the client that emits the block (its accessor reads
  `definition.name`). Not a live request.
* **live** — an isolated round trip against the real endpoint through a private development
  forwarder, with a request synthesised to that exact shape. This is **not** the originating client
  session, which has never emitted the block.
* **assumed** — a decision this transform makes. There is no protocol evidence either way, and it is
  recorded here so that a reviewer can disagree with it on the record.

| Element | Contract | Evidence |
| --- | --- | --- |
| `tool_addition` wrapping `tool_definition` | wrapper stays in place, only its `tool` becomes `tool_reference`; definition hoisted | live |
| flat `tool_definition` inside `content[]` | accepted the same way; the whole block becomes the reference | assumed, unit-tested |
| definition written flat on the wrapped tool | accepted; name and schema are read from the same half of the block | assumed, symmetry fix |
| tool name | `name`, else `tool_name`; when a block carries both, `name` wins | binary, documented |
| name key in the emitted reference | `name` inside the official wrapper, `tool_name` in the flat shape, mirroring the dialect that carried the definition | binary, documented |
| hoisted declaration | every field of the definition except the `definition` wrapper is copied, not rebuilt from a whitelist, so a hoist cannot drop a field | documented |
| declaration identity | two declarations of one name are the same tool when they agree on everything except `type` and `cache_control`, which are transport directives rather than contract | assumed |
| a differing second declaration | refused with 400, naming the position, rather than silently preferring one | assumed |
| `input_schema` | must be a JSON Schema object; a boolean schema is refused, because there is nothing to declare | assumed |
| `tools[]` entries | an entry whose own `type` is `tool_definition` / `tool_addition` is refused; its `input_schema` is never walked | assumed |
| a `tool_reference` entry in `tools[]` | forwarded unchanged | pinned boundary; no live evidence either way |
| walk positions | `messages[].content[]`, `tool_result.content[]`, `tool_addition.tool` only | documented |
| nesting past 8 levels | refused, not skipped: "not inspected" must never read as "clean" | assumed |
| no inline definition present | request returned untouched, byte-identical to baseline, with block order preserved | live |

## Tests

`pytest tests/test_litellm/llms/deepseek/` — 102 passed, covering the conversion, the accepted block
shapes, the official `tool_addition` form, name resolution and the two name spellings, declaration
identity and conflict handling, the fail-closed paths, the deep-nesting guard, and
streaming/non-streaming equivalence.

## Limitations

* The conversion is verified against hand-built requests, a strict mock, and the live A/B above. The
  originating report has **not** been reproduced end-to-end from a real client: a real client driven
  through the same chain used the provider successfully but never emitted an inline block, so the
  trigger was not observed. Treat this as a fix for a shape the transform must handle, not as a
  confirmed production fix.
* Deeper nesting is refused rather than converted — an accepted degradation, not full protocol parity.
* Duplicate declarations of one name that differ in anything but transport metadata are refused rather
  than guessed at. The line between "same tool" and "different tool" is drawn in the contract table
  above; it is a decision, not an observation.
* The **flat** inline shape (`{type: "tool_definition", name, input_schema}` with no `definition`
  wrapper) is supported and unit-tested but has **not** been observed on the live provider, and neither
  has a definition written flat on the wrapped tool. Treat both as **experimental**, unlike the nested
  `definition` shape.
* `tools[]` entries that are neither declarations nor one of the two converted block types are passed
  through unchanged. This transform has no evidence that the provider rejects them and no evidence that
  it accepts them; the boundary is pinned by a test rather than widened on a guess.
* Nothing is deployed.
