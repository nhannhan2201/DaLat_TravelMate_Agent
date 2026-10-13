"""Backend FastAPI gọi workflow đề xuất từ HTTP request."""

from fastapi import FastAPI, HTTPException

from app.config import ConfigurationError
from app.graph import run_recommendation_workflow
from app.llm import NeedExtractionError, PlaceAssessmentError
from app.schemas import RecommendationAPIRequest, RecommendationRequest, RecommendationResponse
from app.serpapi_client import SerpApiError


app = FastAPI(title="DaLat TravelMate Agent", version="0.1.0")


@app.post("/recommendations", response_model=RecommendationResponse)
def create_recommendations(body: RecommendationAPIRequest) -> RecommendationResponse:
    """Chạy đồng bộ trong thread của FastAPI vì workflow dùng requests blocking."""

    if body.location.casefold() != "đà lạt":
        raise HTTPException(status_code=422, detail="MVP hiện chỉ hỗ trợ địa điểm tại Đà Lạt.")
    request = RecommendationRequest(description=body.description, location=body.location)
    try:
        return run_recommendation_workflow(
            request, body.max_candidates_per_group, body.top_k,
        )
    except (SerpApiError, NeedExtractionError, PlaceAssessmentError):
        raise HTTPException(
            status_code=502,
            detail="Không lấy được dữ liệu từ dịch vụ bên ngoài. Hãy kiểm tra cấu hình dịch vụ và thử lại.",
        ) from None
    except ConfigurationError:
        raise HTTPException(status_code=503, detail="Backend chưa có đủ cấu hình API để chạy.") from None
