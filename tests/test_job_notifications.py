"""Tests for isolated Feishu job notification behaviors."""

import json
import os
from pathlib import Path
from unittest.mock import patch


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_job(
    root: Path,
    *,
    mode: str = "real",
    state: str = "succeeded",
) -> Path:
    job_dir = root / "job_20260619_230000_metasurface_sweep"
    write_json(
        job_dir / "manifest.json",
        {
            "job_id": job_dir.name,
            "mode": mode,
            "paths": {"job_dir": str(job_dir)},
        },
    )
    write_json(
        job_dir / "status.json",
        {
            "job_id": job_dir.name,
            "state": state,
            "task_counts": {
                "total": 25,
                "pending": 0,
                "running": 0,
                "succeeded": 24,
                "failed": 1,
                "skipped": 0,
            },
        },
    )
    write_json(
        job_dir / "summary.json",
        {
            "job_id": job_dir.name,
            "task_counts": {
                "total": 25,
                "pending": 0,
                "running": 0,
                "succeeded": 24,
                "failed": 1,
                "skipped": 0,
            },
        },
    )
    write_json(
        job_dir / "quality_report.json",
        {"conclusion": "warning"},
    )
    (job_dir / "run.log").write_text("", encoding="utf-8")
    return job_dir


def test_build_terminal_text_contains_required_job_evidence(tmp_path):
    from src.job_notifications import build_job_notification_text

    job_dir = write_job(tmp_path, state="partial")

    text = build_job_notification_text(job_dir, "partial")

    assert "FDTD job partial" in text
    assert "mode: real" in text
    assert f"job: {job_dir.name}" in text
    assert "tasks: 24 succeeded / 1 failed / 25 total" in text
    assert "quality: warning" in text
    assert f"job_dir: {job_dir}" in text


def test_build_planned_text_uses_total_task_count(tmp_path):
    from src.job_notifications import build_job_notification_text

    job_dir = write_job(tmp_path, mode="mock", state="planned")

    text = build_job_notification_text(job_dir, "planned")

    assert "FDTD job planned" in text
    assert "mode: mock" in text
    assert "tasks: 25 total" in text
    assert "quality:" not in text


def test_notify_posts_text_and_records_success_without_webhook(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    webhook = (
        "https://open.feishu.cn/open-apis/bot/v2/hook/secret-value"
    )

    with patch.dict(
        os.environ, {FEISHU_WEBHOOK_ENV: webhook}, clear=False
    ):
        with patch(
            "src.job_notifications._post_feishu",
            return_value={"status": 200, "body": "{}"},
        ) as post:
            result = notify_job_state(job_dir, "succeeded")

    assert result == {"sent": True, "state": "succeeded"}
    post.assert_called_once()
    assert post.call_args.args[0] == webhook
    record = json.loads(
        (job_dir / "notifications.json").read_text(encoding="utf-8")
    )
    assert record["succeeded"]["sent"] is True
    assert webhook not in json.dumps(record)
    assert (
        webhook
        not in (job_dir / "run.log").read_text(encoding="utf-8")
    )


def test_notify_same_state_is_idempotent_after_success(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    with patch.dict(
        os.environ,
        {FEISHU_WEBHOOK_ENV: "https://open.feishu.cn/test"},
        clear=False,
    ):
        with patch(
            "src.job_notifications._post_feishu",
            return_value={"status": 200, "body": "{}"},
        ) as post:
            first = notify_job_state(job_dir, "succeeded")
            second = notify_job_state(job_dir, "succeeded")

    assert first["sent"] is True
    assert second == {
        "sent": False,
        "state": "succeeded",
        "reason": "already_sent",
    }
    post.assert_called_once()


def test_notify_skips_without_webhook_and_does_not_create_success_record(
    tmp_path,
):
    from src.job_notifications import notify_job_state

    job_dir = write_job(tmp_path)
    with patch.dict(os.environ, {}, clear=True):
        with patch("src.job_notifications._post_feishu") as post:
            result = notify_job_state(job_dir, "succeeded")

    assert result["reason"] == "webhook_not_configured"
    assert not (job_dir / "notifications.json").exists()
    post.assert_not_called()


def test_delivery_failure_is_logged_without_leaking_webhook(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    webhook = (
        "https://open.feishu.cn/open-apis/bot/v2/hook/secret-value"
    )
    with patch.dict(
        os.environ, {FEISHU_WEBHOOK_ENV: webhook}, clear=False
    ):
        with patch(
            "src.job_notifications._post_feishu",
            side_effect=OSError("network unavailable"),
        ):
            result = notify_job_state(job_dir, "failed")

    log = (job_dir / "run.log").read_text(encoding="utf-8")
    assert result["reason"] == "delivery_failed"
    assert webhook not in log
    assert not (job_dir / "notifications.json").exists()


def test_non_notifiable_state_is_skipped(tmp_path):
    from src.job_notifications import notify_job_state

    job_dir = write_job(tmp_path, state="running")

    result = notify_job_state(job_dir, "running")

    assert result["reason"] == "state_not_notifiable"


def test_corrupt_notification_record_is_treated_as_unsent(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    (job_dir / "notifications.json").write_text(
        "{broken", encoding="utf-8"
    )
    with patch.dict(
        os.environ,
        {FEISHU_WEBHOOK_ENV: "https://open.feishu.cn/test"},
        clear=False,
    ):
        with patch(
            "src.job_notifications._post_feishu",
            return_value={"status": 200, "body": "{}"},
        ):
            result = notify_job_state(job_dir, "succeeded")

    assert result["sent"] is True
    assert (
        "notification record unreadable"
        in (job_dir / "run.log").read_text(encoding="utf-8")
    )
