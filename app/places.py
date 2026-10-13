"""Chuyển kết quả Google Maps Search thành ứng viên địa điểm."""

from typing import Any
import json

from app.schemas import EvidenceItem, PlaceCandidate, PlaceEvidence


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    return None


def _number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if minimum <= number <= maximum else None


def parse_search_results(data: dict[str, Any]) -> list[PlaceCandidate]:
    """Lấy các địa điểm có tên từ `local_results` của SerpApi."""

    results = data.get("local_results") or []
    if not isinstance(results, list):
        raise ValueError("local_results không phải danh sách.")

    candidates = []
    for item in results:
        if not isinstance(item, dict):
            continue

        name = _text(item.get("title"))
        if name is None:
            continue

        coordinates = item.get("gps_coordinates")
        if not isinstance(coordinates, dict):
            coordinates = {}

        review_count = item.get("reviews")
        if isinstance(review_count, bool) or not isinstance(review_count, int) or review_count < 0:
            review_count = None

        candidates.append(
            PlaceCandidate(
                name=name,
                place_type=_text(item.get("type")),
                address=_text(item.get("address")),
                rating=_number(item.get("rating"), 0, 5),
                review_count=review_count,
                photo_url=_text(item.get("thumbnail")) or _text(item.get("serpapi_thumbnail")),
                place_id=_text(item.get("place_id")),
                data_id=_text(item.get("data_id")),
                latitude=_number(coordinates.get("latitude"), -90, 90),
                longitude=_number(coordinates.get("longitude"), -180, 180),
            )
        )

    return candidates


def build_place_evidence(
    candidate: PlaceCandidate, details: dict[str, Any], reviews_data: dict[str, Any]
) -> PlaceEvidence:
    """Chọn dữ liệu nguồn cần phân tích, không truyền metadata API cho LLM."""

    place = details.get("place_results") or {}
    reviews = reviews_data.get("reviews") or []
    if not isinstance(place, dict) or not isinstance(reviews, list):
        raise ValueError("Details hoặc reviews không đúng cấu trúc.")
    place_info = reviews_data.get("place_info") or {}
    if not isinstance(place_info, dict):
        raise ValueError("place_info không đúng cấu trúc.")
    for returned_id in (place.get("place_id"), place_info.get("place_id")):
        if returned_id and candidate.place_id and returned_id != candidate.place_id:
            raise ValueError("Dữ liệu trả về không thuộc ứng viên đang đánh giá.")

    items = []
    for field in ("type", "description", "extensions", "hours"):
        value = place.get(field)
        if value is None or value == "" or value == [] or value == {}:
            continue
        if not isinstance(value, (str, list, dict)):
            continue
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        items.append(EvidenceItem(id=f"details:{field}", source="details", text=f"{field}: {text}"))

    seen_review_ids = set()
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            continue
        text = review.get("snippet")
        if not isinstance(text, str) or not text.strip():
            continue
        review_id = _text(review.get("review_id"))
        if review_id and review_id in seen_review_ids:
            continue
        if review_id:
            seen_review_ids.add(review_id)
        items.append(EvidenceItem(
            id=f"review:{index}", source="review", text=text,
            date=_text(review.get("iso_date")) or _text(review.get("date")),
            url=_text(review.get("link")),
        ))
    return PlaceEvidence(
        candidate=candidate, items=items,
        analyzed_review_count=sum(item.source == "review" for item in items),
    )
