"""Ranking theo bằng chứng và tạo output; không gọi thêm API hoặc LLM."""

from urllib.parse import urlencode

from app.schemas import (
    AssessmentGroup, PlaceAssessment, PlaceCandidate, PlaceEvaluation,
    PlaceRecommendation, RecommendationGroup, RecommendationResponse,
)


def _validate_top_k(top_k: int) -> None:
    if type(top_k) is not int or top_k <= 0:
        raise ValueError("top_k phải là số nguyên dương.")


def calculate_match_score(assessment: PlaceAssessment) -> int:
    """Mỗi tiêu chí thuận +1, bất lợi -1; mixed/unknown không góp điểm."""

    score = 0
    for item in assessment.criteria:
        if item.status in ("mixed", "unknown"):
            continue
        favorable = (item.kind == "want" and item.status == "supported") or (
            item.kind == "avoid" and item.status == "contradicted"
        )
        score += 1 if favorable else -1
    return score


def rank_group(group: AssessmentGroup, top_k: int) -> list[PlaceEvaluation]:
    """Xét mọi quán assessed; sort ổn định giữ thứ tự Search khi hòa."""

    _validate_top_k(top_k)
    assessed = [p for p in group.places if p.status == "assessed" and p.assessment is not None]
    return sorted(
        assessed,
        key=lambda p: (
            calculate_match_score(p.assessment),
            p.candidate.rating if p.candidate.rating is not None else -1,
        ),
        reverse=True,
    )[:top_k]


def _join_criteria(criteria: list[str]) -> str:
    values = list(dict.fromkeys(criteria))
    if len(values) <= 1:
        return "".join(values)
    return ", ".join(values[:-1]) + " và " + values[-1]


def _build_reason(assessment: PlaceAssessment) -> str:
    """Tóm tắt theo tiêu chí; giải thích và trích dẫn chi tiết giữ nội bộ."""

    if not assessment.criteria or all(c.status == "unknown" for c in assessment.criteria):
        return "Địa điểm được tìm thấy theo truy vấn của bạn; chưa có đủ thông tin để xác minh các sở thích."

    def criteria(kind: str, status: str) -> str:
        return _join_criteria([
            item.criterion for item in assessment.criteria
            if item.kind == kind and item.status == status
        ])

    statements = []
    favorable_wants = criteria("want", "supported")
    favorable_avoids = criteria("avoid", "contradicted")
    if favorable_wants:
        statements.append(
            f"Thông tin và trải nghiệm được ghi nhận gợi ý đây là lựa chọn đáng cân nhắc "
            f"nếu bạn ưu tiên {favorable_wants}."
        )
    if favorable_avoids:
        statements.append(
            f"Các trải nghiệm được ghi nhận cũng có tín hiệu tích cực với việc tránh {favorable_avoids}."
            if favorable_wants else
            f"Đây là lựa chọn có thể cân nhắc nếu bạn muốn tránh {favorable_avoids}, "
            "dựa trên các trải nghiệm được ghi nhận."
        )
    if not favorable_wants and not favorable_avoids:
        statements.append("Địa điểm được tìm thấy theo truy vấn của bạn, với một số điểm cần cân nhắc thêm.")

    for kind in ("want", "avoid"):
        mixed = criteria(kind, "mixed")
        if mixed:
            subject = mixed if kind == "want" else "điều bạn muốn tránh: " + mixed
            statements.append(f"Trải nghiệm về {subject} chưa đồng nhất.")
    unfavorable_wants = criteria("want", "contradicted")
    unfavorable_avoids = criteria("avoid", "supported")
    if unfavorable_wants:
        statements.append(f"Có phản ánh chưa đáp ứng mong muốn {unfavorable_wants}.")
    if unfavorable_avoids:
        statements.append(f"Bạn nên cân nhắc vì có phản ánh về {unfavorable_avoids}.")
    unknown_wants = criteria("want", "unknown")
    unknown_avoids = criteria("avoid", "unknown")
    if unknown_wants:
        statements.append(f"Bạn nên kiểm tra thêm về {unknown_wants} trước khi quyết định.")
    if unknown_avoids:
        statements.append(f"Chưa đủ thông tin để xác nhận địa điểm tránh được {unknown_avoids}.")
    return " ".join(statements)


def _build_maps_url(candidate: PlaceCandidate) -> str:
    query = ", ".join(value for value in (candidate.name, candidate.address) if value)
    params = {"api": "1", "query": query}
    if candidate.place_id:
        params["query_place_id"] = candidate.place_id
    return "https://www.google.com/maps/search/?" + urlencode(params)


def build_recommendation_response(
    groups: list[AssessmentGroup], location: str, top_k: int
) -> RecommendationResponse:
    """Chọn Top-K mỗi nhóm, giữ ảnh/thông tin và tóm tắt đánh giá thận trọng."""

    _validate_top_k(top_k)
    output_groups = []
    for group in groups:
        selected = rank_group(group, top_k)
        places = []
        for evaluation in selected:
            candidate = evaluation.candidate
            places.append(PlaceRecommendation(
                name=candidate.name, photo_url=candidate.photo_url,
                rating=candidate.rating, review_count=candidate.review_count,
                address=candidate.address, reason=_build_reason(evaluation.assessment),
                google_maps_url=_build_maps_url(candidate),
            ))
        output_groups.append(RecommendationGroup(
            need=group.need.name, places=places,
            message=None if places else "Chưa có địa điểm được đánh giá thành công trong nhóm này.",
        ))
    return RecommendationResponse(location=location, groups=output_groups)
