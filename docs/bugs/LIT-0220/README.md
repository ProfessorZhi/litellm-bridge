# DeepSeek Anthropic Messages: an inline `tool_definition` block is rejected by the provider

## Symptom

A client that surfaces a deferred tool mid-session can declare it inline, as a `tool_definition`
content block, instead of listing it in the request's top-level `tools[]`. DeepSeek's
Anthropic-compatible Messages route has no `tool_definition` content variant, so the body is
refused at the wire-format layer and the turn fails:

```
messages[N].content: unknown variant `tool_definition`, expected `tool_reference`
```

Retrying resends the same body and fails identically. The pinned baseline forwards the client body
unchanged, so the unparseable block reaches the provider.

## Fix

`litellm/llms/deepseek/messages/transformation.py` gains a downgrade step that runs only on this
route. The shape it converts is the documented mid-conversation one: a `tool_addition` whose `tool`
is `{type: "tool_definition", definition: {...}}`. That `definition` is hoisted into `tools[]`
once, and the `tool` becomes `{type: "tool_reference", name: ...}`, leaving the wrapper, the
message and the block order where they were. A request with nothing to convert comes back
byte-identical to baseline.

A `tool_definition` in any other position is refused with a client 400 naming it. DeepSeek answers
a bare `tool_definition` at `messages[].content[]` with `unknown variant 'tool_definition'`, and
the `tool_reference` it would turn into there with `unknown variant 'tool_reference'`, so
converting only moves the same failure one step later. The remaining refusals: no `definition`
object, no non-empty `definition.name`, no object `input_schema`, a `tool_addition` whose `tool` is
neither a definition nor a reference, a redeclaration `tools[]` already holds as a different tool,
a content block sitting in `tools[]`, a non-list `tools`, and nesting past the bounded walk depth.

## Limitations

* Only the nested form converts. A declaration written flat on `tool_addition.tool`
  (`{type: "tool_definition", name, input_schema}`) is refused: the provider has not been observed
  accepting those fields outside a `definition` object.
* Dynamic redefinition is not supported. Anthropic lets a client redefine a tool mid-conversation
  and the newer definition applies from that position onward; a `tools[]` entry has no position, so
  the two cannot both be expressed and a conflicting redeclaration is refused. That is a limit of
  this route, not a claim that the original request was illegal.
* Hoisting moves a declaration out of the conversation and into `tools[]`. Where that moves a
  `cache_control` marker or a `defer_loading` flag out of position, no cache fidelity is promised.
* The originating report is still not reproduced from a real client: the client driven through this
  chain used the provider successfully but never emitted an inline block. The refusals above rest on
  direct probes against the live provider, not on that client.
* Nesting deeper than 8 levels is refused rather than converted.
* Nothing is deployed.

## Tests

`pytest tests/test_litellm/llms/deepseek/`
