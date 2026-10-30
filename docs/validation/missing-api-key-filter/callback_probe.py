import json
import os
import time

from fastapi import HTTPException

from litellm.integrations.custom_logger import CustomLogger

LOG_PATH = os.environ.get("CALLBACK_PROBE_LOG", "/logs/callback-probe.jsonl")
REWRITE = os.environ.get("CALLBACK_PROBE_REWRITE", "false").lower() == "true"


class CallbackProbe(CustomLogger):
    async def async_post_call_failure_hook(
        self,
        request_data,
        user_api_key_dict,
        original_exception,
        traceback_str=None,
    ):
        record = {
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error_class": type(original_exception).__name__,
            "route": getattr(user_api_key_dict, "request_route", None),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        if REWRITE:
            raise HTTPException(status_code=403, detail="callback rewrote the auth failure")
        return None


callback_probe = CallbackProbe()
