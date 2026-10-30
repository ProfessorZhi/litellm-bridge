"""Redact credentials from a log stream without printing them."""

import os
import re
import sys

text = sys.stdin.read()
for name in ("DEEPSEEK_API_KEY", "LITELLM_MASTER_KEY"):
    secret = os.environ.get(name, "")
    if secret:
        text = text.replace(secret, "<redacted>")
text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "<redacted>", text)
text = re.sub(r"Bearer [A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text)
sys.stdout.write(text)
