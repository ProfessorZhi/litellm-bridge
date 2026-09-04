"""
LiteLLM 自定义 spend 日志回调（队列写入器，零丢失）。

- ES = PG 全量镜像：复用 litellm 的 get_logging_payload（字段与 PG SpendLogsPayload 100% 一致）
- 在此基础上叠加胖日志 (request/response 正文) + failed/error
- 回调内不做网络 I/O：追加到队列 records.jsonl (JSONL, O_APPEND)
- 独立进程 spendlog_sender.py 批量发到 bridge 4010 -> ES

用法（config.yaml）:
    success_callback: ["custom_callbacks.spendlog_elk_success"]
    failure_callback: ["custom_callbacks.spendlog_elk_failure"]
"""

import json
import os
import time

QUEUE_DIR = os.getenv("SPENDLOG_QUEUE_DIR", "/app/queue")
QUEUE_FILE = "records.jsonl"


def _enqueue(payload):
    path = os.path.join(QUEUE_DIR, QUEUE_FILE)
    os.makedirs(QUEUE_DIR, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def _iso(ts):
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    try:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=__import__("datetime").timezone.utc)
        return ts.astimezone().isoformat()
    except Exception:
        try:
            return str(ts)
        except Exception:
            return None


def _extract_request(kwargs):
    rk = kwargs.get("request_kwargs") or {}
    out = {}
    if rk.get("messages"):
        out["messages"] = rk["messages"]
    if rk.get("prompt"):
        out["prompt"] = rk["prompt"]
    if rk.get("input"):
        out["input"] = rk["input"]
    if kwargs.get("messages") and not out.get("messages"):
        out["messages"] = kwargs["messages"]
    if kwargs.get("prompt") and not out.get("prompt"):
        out["prompt"] = kwargs["prompt"]
    if kwargs.get("input") and not out.get("input"):
        out["input"] = kwargs["input"]
    return out


def _extract_response(kwargs, response_obj):
    if response_obj is None:
        response_obj = kwargs.get("complete_streaming_response") or kwargs.get("response")
    if response_obj is None:
        return {}
    dump = getattr(response_obj, "model_dump", None)
    if dump is not None:
        try:
            return dump()
        except Exception:
            pass
    if isinstance(response_obj, dict):
        return response_obj
    return {"raw": str(response_obj)}


def _build_payload(kwargs, response_obj, start_time, end_time, failed=False, error=None):
    try:
        from litellm.proxy.spend_tracking.spend_tracking_utils import get_logging_payload

        # 复用 PG 的 get_logging_payload -> 字段与 PG SpendLogsPayload 100% 一致
        # 失败时 completion_start_time/start_time 可能为 None，补非 None 兜底让 get_logging_payload 不崩（这样 api_base/model_group/duration 都能从 litellm_params 带上）
        k2 = dict(kwargs)
        if k2.get("completion_start_time") is None:
            k2["completion_start_time"] = start_time or end_time or datetime.now(timezone.utc)
        if start_time is None and k2.get("completion_start_time") is None:
            k2["completion_start_time"] = datetime.now(timezone.utc)
        payload = dict(get_logging_payload(kwargs=k2, response_obj=response_obj, start_time=start_time, end_time=end_time))
    except Exception as e:
        print("[spendlog_elk] get_logging_payload fallback: %s" % e, flush=True)
        # 失败/异常兜底：最小 payload（保证 ES 有记录）
        lcid = kwargs.get("litellm_call_id") or kwargs.get("id") or ("log-%d" % int(time.time() * 1000))
        payload = {
            "request_id": lcid,
            "call_type": kwargs.get("call_type"),
            "model": kwargs.get("model"),
            "startTime": _iso(start_time),
            "endTime": _iso(end_time),
            "status": "failure" if failed else "success",
            "api_base": (kwargs.get("litellm_params") or {}).get("api_base", ""),
            "api_key": kwargs.get("api_key"),
            "user": kwargs.get("user"),
            "model_group": kwargs.get("model_group"),
        }
    # ES/回调 专属字段：胖日志 + 失败标记（不写进 PG，仅 ES）
    resp = _extract_response(kwargs, response_obj)
    payload["request"] = _extract_request(kwargs)
    payload["response"] = resp
    payload["failed"] = failed
    payload["error"] = error
    if not payload.get("status"):
        payload["status"] = "failure" if failed else "success"
    return payload


async def spendlog_elk_success(kwargs, response_obj, start_time, end_time):
    try:
        payload = _build_payload(kwargs, response_obj, start_time, end_time)
        _enqueue(payload)
        print("[spendlog_elk] queued success %s" % payload["request_id"], flush=True)
    except Exception as e:
        print("[spendlog_elk] success cb err: %s" % e, flush=True)


async def spendlog_elk_failure(kwargs, response_obj, start_time, end_time):
    try:
        error = kwargs.get("exception") or kwargs.get("error")
        _lp = kwargs.get("litellm_params") or {}
        print("[spendlog_elk][DEBUG] fail kwargs: api_base=%r completion_start_time=%r start_time=%r end_time=%r litellm_params_keys=%s" % (
            (_lp.get("api_base") if isinstance(_lp, dict) else None),
            kwargs.get("completion_start_time"),
            start_time, end_time,
            list(_lp.keys()) if isinstance(_lp, dict) else type(_lp)), flush=True)
        payload = _build_payload(kwargs, None, start_time, end_time, failed=True, error=str(error))
        _enqueue(payload)
        print("[spendlog_elk] queued failure %s" % payload["request_id"], flush=True)
    except Exception as e:
        print("[spendlog_elk] failure cb err: %s" % e, flush=True)
