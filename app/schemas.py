"""Dữ liệu vào/ra chung cho agent, API và giao diện."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecommendationRequest(BaseModel):
    """Sở thích người dùng gửi cho agent."""

    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(min_length=1, description="Mô tả sở thích bằng tiếng Việt")
    location: str = Field(default="Đà Lạt", min_length=1)


class RecommendationAPIRequest(RecommendationRequest):
    """Body HTTP: nhu cầu và giới hạn chạy, không chứa API key."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    max_candidates_per_group: int = Field(gt=0, strict=True)
    top_k: int = Field(gt=0, strict=True)


class NeedGroup(BaseModel):
    """Một mục đích tìm kiếm và các tiêu chí người dùng nêu cho mục đích đó."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, description="Tên nhóm, ví dụ: Cà phê")
    wants: list[str] = Field(description="Các điều người dùng muốn")
    avoids: list[str] = Field(description="Các điều người dùng muốn tránh")
    search_query: str = Field(min_length=1, description="Truy vấn Maps gồm loại địa điểm và đặc điểm tìm kiếm chính; không chứa tên thành phố")
    broad_search_query: str = Field(min_length=1, description="Truy vấn rộng giữ cùng loại địa điểm, bỏ đặc điểm bổ sung")


class NeedsAnalysis(BaseModel):
    """Các nhóm nhu cầu được rút ra từ một câu mô tả."""

    groups: list[NeedGroup] = Field(min_length=1)


class PlaceCandidate(BaseModel):
    """Địa điểm từ Maps Search, chưa được phân tích hoặc xếp hạng."""

    name: str
    place_type: str | None = None
    address: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    photo_url: str | None = None
    place_id: str | None = None
    data_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class CandidateGroup(BaseModel):
    """Một nhu cầu và các ứng viên tìm được riêng cho nhu cầu đó."""

    need: NeedGroup
    used_search_query: str
    candidates: list[PlaceCandidate]


class EvidenceItem(BaseModel):
    """Một thông tin gốc, có ID để kết luận tham chiếu lại."""

    id: str
    source: Literal["details", "review"]
    text: str
    date: str | None = None
    url: str | None = None


class PlaceEvidence(BaseModel):
    candidate: PlaceCandidate
    items: list[EvidenceItem]
    analyzed_review_count: int = Field(ge=0)


class CriterionAssessment(BaseModel):
    kind: Literal["want", "avoid"]
    criterion_index: int = Field(ge=0, description="Vị trí tiêu chí trong wants hoặc avoids")
    criterion: str
    status: Literal["supported", "contradicted", "mixed", "unknown"]
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    explanation: str = Field(min_length=1)


class PlaceAssessment(BaseModel):
    """Đánh giá tiêu chí; trạng thái xét tiêu chí, không phải điểm phù hợp."""

    criteria: list[CriterionAssessment]


class PlaceEvaluation(BaseModel):
    """Kết quả xử lý một ứng viên, giữ nguồn cùng đúng địa điểm."""

    candidate: PlaceCandidate
    status: Literal["assessed", "error", "not_evaluated"]
    evidence: PlaceEvidence | None = None
    assessment: PlaceAssessment | None = None
    message: str | None = None


class AssessmentGroup(BaseModel):
    need: NeedGroup
    used_search_query: str
    places: list[PlaceEvaluation]


class PlaceRecommendation(BaseModel):
    """Một địa điểm sẽ được hiển thị cho người dùng."""

    name: str
    photo_url: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    address: str | None = None
    reason: str
    google_maps_url: str | None = None


class RecommendationGroup(BaseModel):
    """Các địa điểm đáp ứng cùng một nhóm nhu cầu."""

    need: str
    places: list[PlaceRecommendation]
    message: str | None = None


class RecommendationResponse(BaseModel):
    """Kết quả agent trả về cho một yêu cầu."""

    location: str
    groups: list[RecommendationGroup]
