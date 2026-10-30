"""Replay the captured compat request through the real transform, no network."""

import copy
import json
import os
from collections import Counter
from pathlib import Path

from litellm.llms.deepseek.messages.transformation import DeepSeekAnthropicMessagesConfig

evidence = Path(os.environ["LIT0226_REAL_EVIDENCE"])
before = json.loads((evidence / "raw" / "compat.request.json").read_text(encoding="utf-8"))
after = DeepSeekAnthropicMessagesConfig.rewrite_deepseek_tool_blocks(
    copy.deepcopy(before), "deepseek-flash"
)
(evidence / "wire" / "before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
(evidence / "wire" / "after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")


def block_types(body: dict) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for message in body.get("messages") or []:
        for block in message.get("content") or []:
            if isinstance(block, dict):
                counts[str(block.get("type"))] += 1
    return dict(sorted(counts.items()))


summary = {
    "before_tools": [tool.get("name") for tool in before.get("tools") or []],
    "after_tools": [tool.get("name") for tool in after.get("tools") or []],
    "before_block_types": block_types(before),
    "after_block_types": block_types(after),
    "tool_definition_after": "tool_definition" in json.dumps(after),
    "tool_reference_after": "tool_reference" in json.dumps(after),
}
(evidence / "wire" / "transform-summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
print(json.dumps(summary, indent=2))
