# DeepSeek Anthropic Messages: an inline `tool_definition` block is rejected by the provider

## Symptom

A client that surfaces a deferred tool mid-session can declare it **inline**, as a
`tool_definition` content block in `messages[].content`, instead of listing it in the request's
top-level `tools[]`. DeepSeek's Anthropic-compatible Messages route has no `tool_definition`
content variant, so the body is refused at the wire-format layer and the turn fails:

```
messages[N].content: unknown variant `tool_definition`, expected `tool_reference`
```

Retrying resends the same body and fails identically. The pinned baseline forwards the client body
unchanged, so the unparseable block reaches the provider.

## Fix

`litellm/llms/deepseek/messages/transformation.py` gains a downgrade step that runs only on this
route. Every inline declaration is rewritten **in place** into a `tool_reference`, keeping message
and block order, and its declaration is hoisted into `tools[]` once. Both documented shapes
convert: a `tool_definition` block standing in `content[]`, and the official mid-conversation form
`{role: "system", content: [{type: "tool_addition", tool: {type: "tool_definition", ...}}]}` where
the wrapper stays and only its `tool` becomes the reference.

The walk is scoped to the positions the provider reads as content blocks (`messages[].content[]`, a
`tool_result`'s nested `content[]`, a `tool_addition`'s `tool`). A `"type": "tool_definition"` pair
anywhere else is user data and is left alone. A request with nothing to convert comes back
byte-identical to baseline.

Anything that cannot be converted losslessly is refused with a client 400 naming the position,
rather than dropped or forwarded: no resolvable name, no object `input_schema`, a block carrying two
disagreeing name spellings, a redeclaration of a name `tools[]` already declares as a different
tool, a declaration in a position that may not declare one, and nesting past the bounded walk depth.

## Limitations

* Dynamic redefinition is not supported. Anthropic lets a client redefine a tool mid-conversation,
  and the newer definition applies from that position onward. A `tools[]` entry has no position, so
  the two cannot both be expressed, and a conflicting redeclaration is refused. That is a
  compatibility limit of this route, not a claim that the original request was illegal.
* Hoisting moves a declaration out of the conversation and into `tools[]`. Where that changes the
  position of a `cache_control` marker or of a `defer_loading` flag, no cache fidelity is promised.
* The flat shape (`{type: "tool_definition", name, input_schema}`, no `definition` wrapper) and a
  definition written flat on a `tool_addition`'s `tool` are supported and unit-tested but have never
  been observed on the live provider. Treat both as experimental, unlike the nested shape.
* The originating report has not been reproduced end to end from a real client: the client driven
  through this chain used the provider successfully but never emitted an inline block.
* Nesting deeper than 8 levels is refused rather than converted.
* Nothing is deployed.

## Tests

`pytest tests/test_litellm/llms/deepseek/`
