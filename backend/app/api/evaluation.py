from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ..config import settings


router = APIRouter(prefix="/api/eval", tags=["evaluation"])


@router.get("/latest")
def latest_report() -> dict:
    path = settings.eval_dir / "report.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="尚未生成评测报告。请在 backend 目录运行：python eval/run_eval.py",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="评测报告格式错误") from exc
