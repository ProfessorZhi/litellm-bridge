"""Assert the live A/B evidence and write a sanitized summary plus checksums."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

evidence = Path(os.environ["LIT0226_REAL_EVIDENCE"])
failures: list[str] = []
checks: list[dict[str, object]] = []


def status(name: str) -> int | None:
    path = evidence / "raw" / f"{name}.status"
    if not path.exists():
        return None
    return int(path.read_text(encoding="utf-8").strip())


def body(name: str) -> str:
    path = evidence / "raw" / f"{name}.response.body"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def check(name: str, condition: bool, detail: str) -> None:
    checks.append({"case": name, "pass": condition, "detail": detail})
    if not condition:
        failures.append(name)
    print(("PASS " if condition else "FAIL ") + name + f"  {detail}")


direct = status("direct")
compat = status("compat")
plain = status("plain")
compat_beta = status("compat-beta")
plain_beta = status("plain-beta")
stream = status("compat-stream")
acl_definition = status("acl-definition")
acl_reference = status("acl-reference")
acl_removal = status("acl-removal")

check("direct-upstream-200", direct == 200, f"HTTP {direct}")
check("compat-inline-tools-200", compat == 200, f"HTTP {compat}")
check("plain-non-opt-in-422", plain == 422, f"HTTP {plain}")
plain_body = body("plain")
check(
    "plain-error-is-tool-definition-discriminator",
    "unknown variant" in plain_body and "tool_definition" in plain_body and "tool_reference" in plain_body,
    "upstream 422 names the tool_definition discriminator",
)
check("compat-beta-200", compat_beta == 200, f"HTTP {compat_beta}")
check("plain-beta-422", plain_beta == 422, f"HTTP {plain_beta}")
check("compat-stream-200", stream == 200, f"HTTP {stream}")
check("compat-stream-message-stop", "message_stop" in body("compat-stream"), "SSE reached message_stop")
check("acl-inline-definition-403", acl_definition == 403, f"HTTP {acl_definition}")
check("acl-inline-reference-403", acl_reference == 403, f"HTTP {acl_reference}")
check("acl-removal-403", acl_removal == 403, f"HTTP {acl_removal}")

model_info_path = evidence / "models" / "model-info.json"
model_info = model_info_path.read_text(encoding="utf-8", errors="replace") if model_info_path.exists() else ""
check(
    "db-deployments-present",
    "v4pro-compat" in model_info and "v4pro-plain" in model_info,
    "isolated DB deployments are visible through /model/info",
)
check(
    "db-deployment-opt-in-marker",
    "anthropic_messages_compatibility" in model_info and "deepseek" in model_info,
    "the compat DB deployment carries the opt-in marker",
)

wire_after_path = evidence / "wire" / "after.json"
wire_after = wire_after_path.read_text(encoding="utf-8", errors="replace") if wire_after_path.exists() else ""
wire_summary_path = evidence / "wire" / "transform-summary.json"
wire_summary = json.loads(wire_summary_path.read_text(encoding="utf-8")) if wire_summary_path.exists() else {}
check("wire-drops-tool-definition", "tool_definition" not in wire_after, "wire body has no tool_definition block")
check("wire-uses-tool-reference", "tool_reference" in wire_after, "wire body uses tool_reference")
check(
    "wire-final-tools",
    "dynamic_tool" in (wire_summary.get("after_tools") or [])
    and "existing_tool" in (wire_summary.get("after_tools") or [])
    and "old_tool" not in (wire_summary.get("after_tools") or []),
    f"after_tools={wire_summary.get('after_tools')}",
)

secret = os.environ.get("DEEPSEEK_API_KEY", "")
leaked: list[str] = []
for path in sorted(evidence.rglob("*")):
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    if secret and secret in text:
        leaked.append(str(path.relative_to(evidence)))
    if re.search(r"sk-[A-Za-z0-9_-]{20,}", text):
        leaked.append(str(path.relative_to(evidence)))
check("no-credential-shaped-values", not leaked, f"leaked={sorted(set(leaked))}")

try:
    model_info_json = json.loads(model_info)
except json.JSONDecodeError:
    model_info_json = {}
model_entries = model_info_json.get("data", []) if isinstance(model_info_json, dict) else []
model_summary = [
    {
        "model_name": entry.get("model_name"),
        "upstream_model": (entry.get("litellm_params") or {}).get("model"),
        "api_base": (entry.get("litellm_params") or {}).get("api_base"),
        "compat": (entry.get("model_info") or {}).get("anthropic_messages_compatibility"),
        "db_model": (entry.get("model_info") or {}).get("db_model"),
    }
    for entry in model_entries
    if isinstance(entry, dict)
]

summary = {
    "statuses": {
        "direct": direct,
        "compat": compat,
        "plain": plain,
        "compat_beta": compat_beta,
        "plain_beta": plain_beta,
        "stream": stream,
        "acl_definition": acl_definition,
        "acl_reference": acl_reference,
        "acl_removal": acl_removal,
    },
    "checks": checks,
    "failures": failures,
    "paid_calls": 4,
    "model_info": model_summary,
    "wire_summary": wire_summary,
}
(evidence / "assertions.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

lines = [
    "# Real DeepSeek Anthropic-compatible A/B evidence",
    "",
    "All requests used an isolated proxy and an isolated Postgres; no production database or deployment was touched.",
    "The upstream is the official DeepSeek Anthropic-compatible endpoint.",
    "",
    "| Case | HTTP | Assertion |",
    "|---|---:|---|",
]
for item in checks:
    lines.append(f"| {item['case']} | {item['detail']} | {'PASS' if item['pass'] else 'FAIL'} |")
lines.extend(
    [
        "",
        "Paid model calls: 4 (direct probe, compat, compat beta, compat stream).",
        "The plain control and the ACL requests are expected to fail before inference.",
        "",
        f"Failures: {len(failures)}",
    ]
)
(evidence / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

checksums = []
for path in sorted(evidence.rglob("*")):
    if path.is_file() and path.name != "SHA256SUMS":
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {path.relative_to(evidence).as_posix()}")
(evidence / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")

print(f"\n{len(checks) - len(failures)} passed, {len(failures)} failed")
sys.exit(1 if failures else 0)
