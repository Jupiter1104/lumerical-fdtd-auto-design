"""Best-effort Feishu notifications for persistent jobs."""

import json
import os
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


FEISHU_WEBHOOK_ENV = "FDTD_FEISHU_WEBHOOK"
NOTIFIABLE_STATES = {"planned", "succeeded", "failed", "partial"}
_NOTIFICATION_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_log(job_dir: Path, message: str) -> None:
    with (job_dir / "run.log").open("a", encoding="utf-8") as output:
        output.write(f"{_utc_now()} {message}\n")


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(
            data, indent=2, sort_keys=True, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def build_job_notification_text(job_dir: Path, state: str) -> str:
    job_dir = Path(job_dir)
    manifest = _read_json(job_dir / "manifest.json")
    summary = _read_json(job_dir / "summary.json")
    counts = summary.get("task_counts") or {}
    lines = [
        f"FDTD job {state}",
        f"mode: {manifest.get('mode', 'unknown')}",
        f"job: {manifest.get('job_id', job_dir.name)}",
    ]
    if state == "planned":
        lines.append(f"tasks: {counts.get('total', 0)} total")
    else:
        lines.append(
            "tasks: {succeeded} succeeded / {failed} failed / "
            "{total} total".format(
                succeeded=counts.get("succeeded", 0),
                failed=counts.get("failed", 0),
                total=counts.get("total", 0),
            )
        )
        quality_path = job_dir / "quality_report.json"
        if quality_path.exists():
            quality = _read_json(quality_path)
            conclusion = quality.get("conclusion", "unavailable")
        else:
            conclusion = "unavailable"
        lines.append(f"quality: {conclusion}")
    lines.append(f"job_dir: {job_dir}")
    return "\n".join(lines)


def _post_feishu(
    webhook_url: str,
    text: str,
    timeout: float = 10.0,
) -> dict:
    payload = {"msg_type": "text", "content": {"text": text}}
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return {
            "status": response.status,
            "body": response.read().decode("utf-8", errors="replace"),
        }


def _read_notification_record(job_dir: Path) -> dict:
    path = job_dir / "notifications.json"
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except (OSError, ValueError, TypeError):
        _append_log(
            job_dir,
            "Feishu notification record unreadable; retrying.",
        )
        return {}


def notify_job_state(
    job_dir: Path,
    state: str,
    *,
    timeout: float = 10.0,
) -> dict:
    job_dir = Path(job_dir)
    if state not in NOTIFIABLE_STATES:
        return {
            "sent": False,
            "state": state,
            "reason": "state_not_notifiable",
        }

    with _NOTIFICATION_LOCK:
        record = _read_notification_record(job_dir)
        if (record.get(state) or {}).get("sent") is True:
            return {
                "sent": False,
                "state": state,
                "reason": "already_sent",
            }

        webhook = os.environ.get(FEISHU_WEBHOOK_ENV, "").strip()
        if not webhook:
            _append_log(
                job_dir,
                f"Skipping Feishu notification: "
                f"{FEISHU_WEBHOOK_ENV} is not set.",
            )
            return {
                "sent": False,
                "state": state,
                "reason": "webhook_not_configured",
            }

        try:
            text = build_job_notification_text(job_dir, state)
            response = _post_feishu(webhook, text, timeout=timeout)
            record[state] = {
                "sent": True,
                "sent_at": _utc_now(),
                "http_status": response["status"],
            }
            _write_json_atomic(
                job_dir / "notifications.json", record
            )
            _append_log(
                job_dir,
                f"Feishu notification sent for state={state}.",
            )
            return {"sent": True, "state": state}
        except Exception as exc:
            _append_log(
                job_dir,
                "Feishu notification failed for "
                f"state={state}: {exc.__class__.__name__}.",
            )
            return {
                "sent": False,
                "state": state,
                "reason": "delivery_failed",
            }
