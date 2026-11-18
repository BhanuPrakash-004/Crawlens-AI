from pathlib import Path
from backend.app.schemas import Report

def sample_report():
    return Report.model_validate_json((Path(__file__).resolve().parents[2] / "frontend/src/test/fixtures/report.json").read_text(encoding="utf-8"))
