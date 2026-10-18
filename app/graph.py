"""Tách nhu cầu, tìm địa điểm cho từng nhóm rồi chuẩn hóa kết quả."""

from typing import Any, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import get_deepseek_api_key, get_deepseek_base_url, get_deepseek_model, get_serpapi_api_key
from app.llm import PlaceAssessmentError, assess_place, extract_needs
from app.places import build_place_evidence, parse_search_results
from app.ranking import build_recommendation_response
from app.schemas import AssessmentGroup, CandidateGroup, NeedGroup, PlaceCandidate, PlaceEvaluation, PlaceEvidence, RecommendationRequest, RecommendationResponse
from app.serpapi_client import SerpApiError, SerpApiNoResults, get_place_details, get_place_reviews, search_places


class SearchState(TypedDict):
    """Dữ liệu được truyền giữa các node trong một lần chạy."""

    description: str
    location: str
    needs: NotRequired[list[NeedGroup]]
    search_responses: NotRequired[list[dict[str, Any]]]
    used_search_queries: NotRequired[list[str]]
    groups: NotRequired[list[CandidateGroup]]


class PreparedPlace(TypedDict):
    candidate: PlaceCandidate
    status: Literal["ready", "error", "not_evaluated"]
    evidence: PlaceEvidence | None
    message: str | None


class AssessmentState(SearchState):
    max_candidates_per_group: int
    prepared_groups: NotRequired[list[list[PreparedPlace]]]
    assessment_groups: NotRequired[list[AssessmentGroup]]
    top_k: NotRequired[int]
    response: NotRequired[RecommendationResponse]


def _extract_needs_node(state: SearchState) -> dict[str, list[NeedGroup]]:
    return {"needs": extract_needs(state["description"]).groups}


def _search_node(state: SearchState) -> dict[str, Any]:
    responses = []
    used_queries = []
    for need in state["needs"]:
        query = need.search_query
        try:
            response = search_places(query, state["location"])
        except SerpApiNoResults:
            response = {"local_results": []}
        if not parse_search_results(response) and need.broad_search_query != query:
            query = need.broad_search_query
            try:
                response = search_places(query, state["location"])
            except SerpApiNoResults:
                response = {"local_results": []}
        responses.append(response)
        used_queries.append(query)
    return {"search_responses": responses, "used_search_queries": used_queries}


def _normalize_node(state: SearchState) -> dict[str, list[CandidateGroup]]:
    needs = state["needs"]
    responses = state["search_responses"]
    queries = state["used_search_queries"]
    if len(needs) != len(responses) or len(needs) != len(queries):
        raise ValueError("Số phản hồi Search không khớp với số nhóm nhu cầu.")

    groups = [
        CandidateGroup(need=need, used_search_query=query, candidates=parse_search_results(response))
        for need, response, query in zip(needs, responses, queries)
    ]
    return {"groups": groups}


def _search_builder(state_schema):
    builder = StateGraph(state_schema)
    builder.add_node("extract_needs", _extract_needs_node)
    builder.add_node("search", _search_node)
    builder.add_node("normalize", _normalize_node)
    builder.add_edge(START, "extract_needs")
    builder.add_edge("extract_needs", "search")
    builder.add_edge("search", "normalize")
    return builder


def build_search_graph():
    """Nối ba node theo thứ tự Extract Needs → Search → Normalize."""

    builder = _search_builder(SearchState)
    builder.add_edge("normalize", END)
    return builder.compile()


def _evidence_node(state: AssessmentState) -> dict[str, list[list[PreparedPlace]]]:
    prepared_groups = []
    cache: dict[str, PlaceEvidence] = {}
    for group in state["groups"]:
        prepared = []
        seen = set()
        selected = 0
        for candidate in group.candidates:
            place_id = (candidate.place_id or "").strip()
            message = None
            if not place_id:
                message = "Thiếu place_id."
            elif place_id in seen:
                message = "Trùng place_id trong nhóm."
            elif selected >= state["max_candidates_per_group"]:
                message = "Vượt giới hạn ứng viên được phân tích trong nhóm."
            if place_id:
                seen.add(place_id)
            if message:
                prepared.append(PreparedPlace(candidate=candidate, status="not_evaluated", evidence=None, message=message))
                continue
            selected += 1
            try:
                if place_id not in cache:
                    details = get_place_details(place_id)
                    reviews = get_place_reviews(place_id)
                    cache[place_id] = build_place_evidence(candidate, details, reviews)
                evidence = cache[place_id].model_copy(update={"candidate": candidate}, deep=True)
                prepared.append(PreparedPlace(candidate=candidate, status="ready", evidence=evidence, message=None))
            except (SerpApiError, ValueError) as exc:
                prepared.append(PreparedPlace(candidate=candidate, status="error", evidence=None, message=str(exc)))
        prepared_groups.append(prepared)
    return {"prepared_groups": prepared_groups}


def _assessment_node(state: AssessmentState) -> dict[str, list[AssessmentGroup]]:
    groups = []
    for group, prepared in zip(state["groups"], state["prepared_groups"], strict=True):
        places = []
        for item in prepared:
            if item["status"] != "ready":
                places.append(PlaceEvaluation(
                    candidate=item["candidate"], status=item["status"], message=item["message"],
                ))
                continue
            evidence = item["evidence"]
            if evidence is None:
                raise ValueError("Ứng viên sẵn sàng đánh giá phải có bằng chứng.")
            try:
                assessment = assess_place(group.need, evidence)
                places.append(PlaceEvaluation(candidate=item["candidate"], status="assessed", evidence=evidence, assessment=assessment))
            except (PlaceAssessmentError, ValueError) as exc:
                places.append(PlaceEvaluation(candidate=item["candidate"], status="error", evidence=evidence, message=str(exc)))
        groups.append(AssessmentGroup(need=group.need, used_search_query=group.used_search_query, places=places))
    return {"assessment_groups": groups}


def _assessment_builder():
    builder = _search_builder(AssessmentState)
    builder.add_node("evidence", _evidence_node)
    builder.add_node("assess", _assessment_node)
    builder.add_edge("normalize", "evidence")
    builder.add_edge("evidence", "assess")
    return builder


def build_assessment_graph():
    """Search → Normalize → Evidence → Assess, xử lý tuần tự theo nhóm."""

    builder = _assessment_builder()
    builder.add_edge("assess", END)
    return builder.compile()


def _recommendation_node(state: AssessmentState) -> dict[str, RecommendationResponse]:
    return {"response": build_recommendation_response(
        state["assessment_groups"], state["location"], state["top_k"],
    )}


def build_recommendation_graph():
    builder = _assessment_builder()
    builder.add_node("recommend", _recommendation_node)
    builder.add_edge("assess", "recommend")
    builder.add_edge("recommend", END)
    return builder.compile()


def run_assessment_workflow(
    request: RecommendationRequest, max_candidates_per_group: int
) -> AssessmentState:
    """Giới hạn số ứng viên được thử phân tích, không thay thế quán lỗi."""

    _validate_assessment_request(request, max_candidates_per_group)
    return build_assessment_graph().invoke({
        "description": request.description, "location": "Đà Lạt",
        "max_candidates_per_group": max_candidates_per_group,
    })


def _validate_assessment_request(request: RecommendationRequest, max_candidates_per_group: int) -> None:
    if type(max_candidates_per_group) is not int or max_candidates_per_group <= 0:
        raise ValueError("max_candidates_per_group phải là số nguyên dương.")
    if request.location.casefold() != "đà lạt":
        raise ValueError("MVP hiện chỉ hỗ trợ địa điểm tại Đà Lạt.")
    # Kiểm tra đủ cấu hình trước bất kỳ lời gọi API nào.
    get_serpapi_api_key()
    get_deepseek_api_key()
    get_deepseek_base_url()
    get_deepseek_model()


def run_recommendation_workflow(
    request: RecommendationRequest, max_candidates_per_group: int, top_k: int
) -> RecommendationResponse:
    """Chạy toàn bộ agent và trả Top-K theo từng nhóm, không lộ điểm nội bộ."""

    initial = prepare_recommendation_state(request, max_candidates_per_group, top_k)
    state = build_recommendation_graph().invoke(initial)
    return state["response"]


def prepare_recommendation_state(
    request: RecommendationRequest, max_candidates_per_group: int, top_k: int
) -> AssessmentState:
    """Kiểm tra input/cấu hình dùng chung; không gọi API và không trả API key."""

    if type(top_k) is not int or top_k <= 0:
        raise ValueError("top_k phải là số nguyên dương.")
    _validate_assessment_request(request, max_candidates_per_group)
    return {
        "description": request.description, "location": "Đà Lạt",
        "max_candidates_per_group": max_candidates_per_group,
        "top_k": top_k,
    }


def run_search_workflow(request: RecommendationRequest) -> SearchState:
    """Tìm ứng viên theo từng nhu cầu trong mô tả tiếng Việt tại Đà Lạt."""

    if request.location.casefold() != "đà lạt":
        raise ValueError("MVP hiện chỉ hỗ trợ địa điểm tại Đà Lạt.")

    graph = build_search_graph()
    return graph.invoke({"description": request.description, "location": "Đà Lạt"})
