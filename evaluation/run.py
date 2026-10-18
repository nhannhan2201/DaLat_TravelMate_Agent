"""Chạy graph một lần/case và xuất dữ liệu để người dùng tự chấm.

Không gọi qua FastAPI, không tự chấm, không lưu raw phản hồi API.
"""

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from pydantic import BaseModel

from app.config import ConfigurationError
from app.graph import build_recommendation_graph, prepare_recommendation_state
from app.llm import NeedExtractionError, PlaceAssessmentError
from app.ranking import rank_group
from app.schemas import RecommendationRequest
from app.serpapi_client import SerpApiError


ROOT = Path(__file__).resolve().parents[1]
STATE_FIELDS = (
    "needs", "used_search_queries", "groups", "prepared_groups",
    "assessment_groups", "response",
)
NODES = ("extract_needs", "search", "normalize", "evidence", "assess", "recommend")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    """Redact secret đã cấu hình và tham số nhạy cảm, kể cả trong chuỗi nguồn."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            k: clean(v) for k, v in value.items()
            if k.casefold() not in {"api_key", "authorization", "access_token", "password"}
        }
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, str):
        for name in ("SERPAPI_API_KEY", "DEEPSEEK_API_KEY"):
            secret = os.getenv(name, "").strip()
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)([?&](?:api_key|key|access_token|token)=)[^\s&#\"<>]+", r"\1[REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)
        return value
    return value


def write_json(path: Path, data: dict) -> None:
    # File tạm trong cùng thư mục: bản JSON trước còn đọc được nếu bị ngắt khi ghi.
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(clean(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or [c.get("id") for c in cases if isinstance(c, dict)] != [f"E{i:02}" for i in range(1, 11)]:
        raise ValueError("Bộ câu hỏi phải chứa đúng E01–E10, theo thứ tự và không trùng.")
    if len(cases) != 10:
        raise ValueError("Bộ câu hỏi phải có đúng 10 câu.")
    for case in cases:
        RecommendationRequest(description=case["description"], location=case["location"])
        if not isinstance(case.get("expected_groups"), list) or not case["expected_groups"]:
            raise ValueError("Case thiếu nhóm mong đợi.")
    return cases


def safe_error(exc: Exception) -> dict:
    # Không ghi str(exc)/traceback: SDK có thể đính kèm request và secret.
    categories = (
        (ConfigurationError, "configuration", "Thiếu cấu hình API bắt buộc."),
        (SerpApiError, "serpapi", "Không lấy được dữ liệu SerpApi."),
        (NeedExtractionError, "need_extraction", "Không nhận được nhu cầu hợp lệ từ mô hình."),
        (PlaceAssessmentError, "assessment", "Không nhận được assessment hợp lệ."),
        (ValueError, "validation", "Input hoặc dữ liệu giữa các bước không hợp lệ."),
    )
    for kind, category, message in categories:
        if isinstance(exc, kind):
            return {"category": category, "message": message}
    return {"category": "unexpected", "message": "Lỗi không dự kiến; không xuất exception thô."}


def recommendation_links(state: dict, top_k: int) -> list[dict]:
    """Nối theo vị trí nhóm và kết quả rank_group, không dò tên địa điểm."""
    links = []
    for index, (group, output_group) in enumerate(zip(
        state["assessment_groups"], state["response"].groups, strict=True,
    )):
        selected = rank_group(group, top_k)
        for rank, (place, output) in enumerate(zip(selected, output_group.places, strict=True), 1):
            candidate_index = next(i for i, p in enumerate(group.places) if p is place)
            links.append({
                "group_index": index, "group_name": group.need.name,
                "assessment_place_index": candidate_index,
                "place_id": place.candidate.place_id, "rank": rank,
                "output": output.model_dump(mode="json"),
            })
    return links


def run_case(case: dict, max_candidates: int, top_k: int, path: Path) -> dict:
    record = {
        "id": case["id"],
        "request": {"description": case["description"], "location": case["location"]},
        "expected_groups": case["expected_groups"], "notes": case.get("notes", ""),
        "started_at": utc_now(), "finished_at": None, "status": "running",
        "completed_nodes": [], "failed_stage": None, "error": None,
        "data": {}, "missing_fields": list(STATE_FIELDS), "recommendation_links": [],
    }
    state = {}
    stage = "prepare_input"
    write_json(path, record)
    try:
        request = RecommendationRequest(**record["request"])
        initial = prepare_recommendation_state(request, max_candidates, top_k)
        # updates trả từng node đã hoàn thành; không chạy invoke thêm lần nữa.
        stage = NODES[0]
        for update in build_recommendation_graph().stream(initial, stream_mode="updates"):
            for node, fields in update.items():
                if node not in NODES:
                    continue
                # search_responses chứa raw API metadata: không đưa vào state xuất.
                state.update({k: v for k, v in fields.items() if k in STATE_FIELDS})
                record["completed_nodes"].append(node)
                record["data"] = clean(state)
                record["missing_fields"] = [k for k in STATE_FIELDS if k not in state]
                write_json(path, record)
                print(f"  {case['id']}: {node}", flush=True)
                position = NODES.index(node) + 1
                stage = NODES[position] if position < len(NODES) else "finalize"
        if record["missing_fields"]:
            raise ValueError("Graph chưa trả đủ dữ liệu.")
        record["recommendation_links"] = recommendation_links(state, top_k)
        issues = any(
            any(p.status == "error" for p in g.places)
            for g in state["assessment_groups"]
        ) or not state["response"].groups or any(not g.places for g in state["response"].groups)
        record["status"] = "completed_with_issues" if issues else "completed"
    except KeyboardInterrupt:
        record["status"] = "interrupted"
        record["failed_stage"] = stage
        record["error"] = {"category": "interrupted", "message": "Người dùng ngắt lần chạy."}
    except Exception as exc:
        record["status"] = "error"
        record["failed_stage"] = stage
        record["error"] = safe_error(exc)
    record["finished_at"] = utc_now()
    write_json(path, record)
    return clean(record)


def md(value) -> str:
    """Nguồn là dữ liệu không đáng tin: escape HTML, bảng và Markdown."""
    text = html.escape(str(value))
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text).replace("\n", "<br>")


def render_report(records: list[dict], manifest: dict) -> str:
    lines = [
        "# Báo cáo để chấm thủ công", "",
        f"Lần chạy: {md(manifest['run_id'])}", "",
        "Nhãn chấm: Đạt / Chưa đạt / Chưa xác định. Ô trống = chưa chấm.", "",
        "Status chỉ mô tả thực thi, không phải nhãn chất lượng. Không có số liệu accuracy.", "",
        "Index nhóm/địa điểm bắt đầu từ 0. ID nguồn chỉ có nghĩa trong đúng địa điểm.", "",
    ]
    for rec in records:
        data = rec["data"]
        lines += [f"## {rec['id']}", "", md(rec["request"]["description"]), "",
                  f"Trạng thái thực thi: {md(rec['status'])}", "",
                  f"Kỳ vọng: {md(json.dumps(rec['expected_groups'], ensure_ascii=False))}", "",
                  f"Ghi chú: {md(rec['notes'])}", ""]
        if rec["error"]:
            lines += [f"Lỗi ở bước {md(rec['failed_stage'])}: {md(rec['error']['category'])} — {md(rec['error']['message'])}", ""]
        if rec["missing_fields"]:
            lines += [f"Chưa thu được: {md(', '.join(rec['missing_fields']))}", ""]
        lines += ["### Hiểu nhu cầu", "", "| Nhóm thực tế | Wants | Avoids | Query cụ thể / rộng / đã dùng | Kết quả chấm | Nhận xét |",
                  "|---|---|---|---|---|---|"]
        needs = data.get("needs", [])
        queries = data.get("used_search_queries", [])
        for i, need in enumerate(needs):
            used = queries[i] if i < len(queries) else "Chưa thu được"
            lines.append(f"| {i}: {md(need['name'])} | {md('; '.join(need['wants']))} | {md('; '.join(need['avoids']))} | {md(need['search_query'])}<br>{md(need['broad_search_query'])}<br>{md(used)} | | |")
        lines += ["", "### Ứng viên và bằng chứng", ""]
        groups = data.get("assessment_groups")
        if groups is None:
            # Node assess có thể lỗi; vẫn trình bày evidence từ node trước.
            prepared = data.get("prepared_groups", [])
            groups = [{"need": g["need"], "places": prepared[i] if i < len(prepared) else [
                {"candidate": p, "status": "not_collected", "evidence": None}
                for p in g["candidates"]
            ]} for i, g in enumerate(data.get("groups", []))]
        if not groups:
            lines += ["Không có nhóm ứng viên để trình bày. Xem trạng thái và dữ liệu thiếu ở trên.", ""]
        for gi, group in enumerate(groups):
            lines += [f"#### Nhóm {gi}: {md(group['need']['name'])}", ""]
            if not group["places"]:
                lines += ["Không có ứng viên trong nhóm.", ""]
            for pi, place in enumerate(group["places"]):
                c = place["candidate"]
                lines += [f"##### Địa điểm {gi}/{pi}: {md(c['name'])}", "",
                          f"place_id: {md(c.get('place_id') or 'Thiếu')} — status: {md(place['status'])}", "",
                          f"Địa chỉ: {md(c.get('address') or 'Thiếu')}", ""]
                if place.get("message"):
                    lines += [f"Thông báo: {md(place['message'])}", ""]
                evidence = place.get("evidence")
                if evidence is None:
                    lines += ["Chưa thu được evidence; không đồng nghĩa địa điểm không có thông tin.", ""]
                    items = {}
                else:
                    items = {item["id"]: item for item in evidence["items"]}
                    lines += [f"Số review phân tích: {evidence['analyzed_review_count']} (không phải tổng review Google).", ""]
                    if not items:
                        lines += ["Evidence đã chuẩn bị nhưng rỗng.", ""]
                    for item in evidence["items"]:
                        lines += [f"- **{md(item['id'])}** ({md(item['source'])}): {md(item['text'])}<br>Ngày: {md(item.get('date') or 'Thiếu')}<br>URL: {md(item.get('url') or 'Thiếu')}", ""]
                assessment = place.get("assessment")
                if assessment is None:
                    lines += ["Chưa có assessment.", ""]
                else:
                    lines += ["| Loại / index / tiêu chí | Trạng thái | Giải thích | Nguồn hỗ trợ (nguyên văn) | Nguồn phản bác (nguyên văn) | Chấm bám nguồn | Nhận xét |",
                              "|---|---|---|---|---|---|---|"]
                    for cr in assessment["criteria"]:
                        def sources(field):
                            return "<br>".join(md(f"{key}: {items[key]['text']}" if key in items else f"{key}: KHÔNG TÌM THẤY NGUỒN") for key in cr[field]) or "—"
                        lines.append(f"| {md(cr['kind'])} / {cr['criterion_index']} / {md(cr['criterion'])} | {md(cr['status'])} | {md(cr['explanation'])} | {sources('supporting_evidence_ids')} | {sources('contradicting_evidence_ids')} | | |")
                    lines.append("")
        lines += ["### Đề xuất cuối", ""]
        response = data.get("response")
        if response is None:
            lines += ["Chưa thu được response cuối.", ""]
        else:
            for gi, group in enumerate(response["groups"]):
                lines += [f"#### Nhóm {gi}: {md(group['need'])}", ""]
                if not group["places"]:
                    lines += [md(group.get("message") or "Nhóm không có đề xuất."), ""]
        for link in rec["recommendation_links"]:
            out = link["output"]
            lines += [f"##### Nhóm {link['group_index']} / Top {link['rank']}: {md(out['name'])}", "",
                      f"Tham chiếu assessment: {link['group_index']}/{link['assessment_place_index']}; place_id: {md(link['place_id'] or 'Thiếu')}", "",
                      f"Rating: {md(out.get('rating'))}; số đánh giá: {md(out.get('review_count'))} (không phải nhãn chất lượng).", "",
                      f"Địa chỉ: {md(out.get('address') or 'Thiếu')}", "",
                      f"Ảnh URL: {md(out.get('photo_url') or 'Thiếu')}", "",
                      f"Maps URL: {md(out.get('google_maps_url') or 'Thiếu')}", "",
                      f"Lý do: {md(out['reason'])}", "",
                      "| Ghi chú output/UI (ngoài benchmark, không chấm điểm) |",
                      "|---|", "| |", ""]
        lines += ["| Lỗi / dữ liệu thiếu cần lưu ý | Ảnh hưởng đến việc chấm |", "|---|---|", "| | |", ""]
    return "\n".join(lines) + "\n"


def code_version() -> dict:
    try:
        def git(*args):
            return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.DEVNULL, text=True).strip()
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def run_evaluation(cases: list[dict], max_candidates: int, top_k: int, output_root: Path) -> Path:
    if any(type(v) is not int or v <= 0 for v in (max_candidates, top_k)):
        raise ValueError("Hai giới hạn phải là số nguyên dương.")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    folder = output_root / run_id
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id, "started_at": utc_now(), "finished_at": None,
        "max_candidates_per_group": max_candidates, "top_k": top_k,
        "code": code_version(), "model": None,
        "status": "running", "cases": [{"id": c["id"], "status": "pending"} for c in cases],
    }
    records = []
    write_json(folder / "manifest.json", manifest)
    for index, case in enumerate(cases):
        print(f"Đang chạy {case['id']}…", flush=True)
        record = run_case(case, max_candidates, top_k, folder / f"{case['id']}.json")
        records.append(record)
        manifest["cases"][index] = {"id": case["id"], "status": record["status"]}
        manifest["model"] = clean(os.getenv("DEEPSEEK_MODEL", "").strip()) or None
        write_json(folder / "manifest.json", manifest)
        (folder / "report.md").write_text(render_report(records, manifest), encoding="utf-8")
        if record["status"] == "interrupted":
            break
    manifest["finished_at"] = utc_now()
    statuses = [c["status"] for c in manifest["cases"]]
    manifest["status"] = "interrupted" if "interrupted" in statuses else "completed_with_issues" if any(s != "completed" for s in statuses) else "completed"
    write_json(folder / "manifest.json", manifest)
    (folder / "report.md").write_text(render_report(records, manifest), encoding="utf-8")
    print(f"Đã lưu: {folder}", flush=True)
    return folder


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Phải là số nguyên dương.")
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chạy Agent thật và lưu dữ liệu để tự chấm (có sử dụng hạn mức API).")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", choices=[f"E{i:02}" for i in range(1, 11)])
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--max-candidates-per-group", required=True, type=positive_int)
    parser.add_argument("--top-k", required=True, type=positive_int)
    args = parser.parse_args(argv)
    cases = load_cases(ROOT / "evaluation" / "cases.json")
    selected = cases if args.all else [c for c in cases if c["id"] == args.case]
    folder = run_evaluation(selected, args.max_candidates_per_group, args.top_k, ROOT / "evaluation" / "runs")
    status = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["status"]
    return 130 if status == "interrupted" else 1 if status == "completed_with_issues" else 0


if __name__ == "__main__":
    raise SystemExit(main())
