"""Gọi SerpApi để tìm địa điểm, lấy thông tin chi tiết và review."""

from typing import Any

import requests

from app.config import get_serpapi_api_key


_SEARCH_URL = "https://serpapi.com/search.json"
_SEARCH_ORIGINS = {"đà lạt": "@11.9404,108.4583,14z"}


class SerpApiError(RuntimeError):
    """Lỗi khi không lấy được kết quả tìm kiếm từ SerpApi."""


class SerpApiNoResults(SerpApiError):
    """Google Maps không tìm thấy địa điểm cho truy vấn."""


def search_places(query: str, location: str) -> dict[str, Any]:
    """Tìm địa điểm bằng Google Maps Search và trả về JSON gốc.

    Chưa chuẩn hóa hay xếp hạng kết quả; bước này dùng để khảo sát dữ liệu thật.
    """

    query = query.strip()
    location = location.strip()
    if not query or not location:
        raise ValueError("Truy vấn và location không được để trống.")

    params = {
        "engine": "google_maps",
        "type": "search",
        "q": f"{query} {location}",
        "hl": "vi",
        "gl": "vn",
    }
    search_origin = _SEARCH_ORIGINS.get(location.casefold())
    if search_origin:
        params["ll"] = search_origin

    return _request(params, allow_no_results=True)


def get_place_details(place_id: str) -> dict[str, Any]:
    """Lấy JSON gốc của Place Details cho một địa điểm."""

    place_id = place_id.strip()
    if not place_id:
        raise ValueError("place_id không được để trống.")
    return _request({
        "engine": "google_maps",
        "type": "place",
        "place_id": place_id,
        "hl": "vi",
        "gl": "vn",
    })


def get_place_reviews(place_id: str) -> dict[str, Any]:
    """Lấy JSON gốc của trang review đầu tiên; chưa lấy các trang tiếp theo."""

    place_id = place_id.strip()
    if not place_id:
        raise ValueError("place_id không được để trống.")
    return _request({
        "engine": "google_maps_reviews",
        "place_id": place_id,
        "hl": "vi",
    })


def _request(params: dict[str, Any], *, allow_no_results: bool = False) -> dict[str, Any]:
    """Dùng chung xử lý key, kết nối, JSON và lỗi SerpApi."""

    api_key = get_serpapi_api_key()
    params = {**params, "api_key": api_key}

    try:
        response = requests.get(_SEARCH_URL, params=params, timeout=20)
    except requests.Timeout:
        raise SerpApiError("SerpApi quá thời gian chờ.") from None
    except requests.RequestException:
        # Không đưa URL trong exception ra ngoài vì URL chứa API key.
        raise SerpApiError("Không kết nối được với SerpApi.") from None

    try:
        data = response.json()
    except ValueError:
        raise SerpApiError("SerpApi trả về dữ liệu không phải JSON.") from None

    if not isinstance(data, dict):
        raise SerpApiError("SerpApi trả về JSON không đúng cấu trúc.")

    error = data.get("error")
    if allow_no_results and response.status_code == 200 and error == "Google hasn't returned any results for this query.":
        raise SerpApiNoResults("Google Maps không có kết quả cho truy vấn này.")
    if response.status_code >= 400 or error:
        detail = str(error).replace(api_key, "[REDACTED]") if error else "Không có chi tiết lỗi."
        raise SerpApiError(f"SerpApi lỗi HTTP {response.status_code}: {detail}")

    return data
