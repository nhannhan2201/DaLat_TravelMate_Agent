"""Giao diện Streamlit; chỉ gửi HTTP tới FastAPI, không gọi Agent trực tiếp."""

import html
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
BACKEND_URL = (os.getenv("BACKEND_URL", "").strip() or "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="Đà Lạt · TravelMate", page_icon="🌲", layout="wide")

st.markdown("""
<style>
.stApp { background: #f7f5ef; }
.block-container { max-width: 1120px; padding-top: 2rem; padding-bottom: 3rem; }
header[data-testid="stHeader"] { background: transparent; }
.brand { display:flex; align-items:center; gap:12px; margin:0 0 24px; color:#285c4d; }
.brand-mark { font-size:27px; background:#e5ebe0; padding:5px 12px; border-radius:12px; }
.brand-name { font-weight:750; font-size:20px; letter-spacing:-.5px; }
.brand-note { font-size:12px; color:#66796c; }
.hero { position:relative; overflow:hidden; border-radius:26px; background:#e6ece2;
        padding:44px 42px 54px; min-height:300px; margin-bottom:26px; }
.hero svg { position:absolute; right:0; bottom:0; width:65%; height:100%; opacity:.75; }
.hero-copy { position:relative; z-index:1; max-width:640px; }
.eyebrow { font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:#54735c; }
.hero h1 { font-family:Georgia,serif; font-size:clamp(34px,4.8vw,54px); line-height:1.12;
           font-weight:500; color:#234b3c; margin:15px 0 15px; letter-spacing:-1.5px; }
.hero p { max-width:460px; font-size:15px; line-height:1.7; color:#4b6656; margin:0; }
.hero-pill { display:inline-block; margin-top:22px; padding:6px 12px; border:1px solid #aabda8;
             border-radius:30px; font-size:12px; background:#f7f5ef99; color:#3e624f; }
div[data-testid="stForm"] { background:#fffdf9; border:1px solid #e2e3d7; border-radius:20px; padding:24px; }
div[data-testid="stTextArea"] textarea { background:#faf9f4; border-radius:12px; font-size:15px; }
div[data-testid="stFormSubmitButton"] button { border-radius:12px; min-height:46px; font-weight:650; }
.section-title { font-family:Georgia,serif; color:#234b3c; font-size:29px; font-weight:500; margin:22px 0 5px; }
.section-note { color:#718073; font-size:13px; margin-bottom:22px; }
.empty { margin:24px 0 8px; padding:25px; border:1px dashed #ccd5c5; border-radius:18px;
         color:#667a67; text-align:center; background:#f0f2e9; line-height:1.8; }
.place-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:24px; margin:16px 0 30px; }
.place-card { background:#fffdf9; border:1px solid #e1e4d8; border-radius:20px; overflow:hidden;
              box-shadow:0 5px 18px #263d2910; display:flex; flex-direction:column; }
.photo { height:250px; background:linear-gradient(130deg,#d9e5d6,#eef0e5); position:relative;
         display:flex; align-items:center; justify-content:center; color:#5f785f; overflow:hidden; }
.photo img { width:100%; height:100%; object-fit:cover; color:#4b6656; font-size:14px; }
.photo .photo-placeholder { font-size:14px; }
.place-body { padding:24px; flex:1; display:flex; flex-direction:column; }
.place-name { font-size:21px; font-family:Georgia,serif; font-weight:600; color:#263f33; margin:0 0 12px; line-height:1.3; }
.rating { color:#755d2b; font-size:13px; margin:0 0 13px; }
.rating span { color:#7b8277; }
.address { color:#68776b; font-size:13px; line-height:1.6; margin:0 0 18px; }
.reason { color:#3d5546; font-size:14px; line-height:1.8; border-top:1px solid #ecece3; padding-top:16px; margin-bottom:22px; }
.maps-link { color:#285c4d !important; background:#edf2e8; border:1px solid #d7e2d1; border-radius:10px;
             padding:11px 16px; text-decoration:none !important; font-size:13px; font-weight:600;
             align-self:flex-start; margin-top:auto; }
.maps-link:hover { background:#dfe9d9; }
.footer { margin-top:40px; padding-top:20px; border-top:1px solid #e0e3d8; color:#7c867a;
          font-size:12px; line-height:1.7; }
@media(max-width:700px) {
  .block-container { padding-left:1rem; padding-right:1rem; padding-top:1rem; }
  .hero { padding:30px 24px; min-height:290px; }
  .hero svg { width:100%; opacity:.35; }
  .place-grid { grid-template-columns:1fr; gap:18px; }
  .photo { height:230px; }
}
</style>
<div class="brand"><span class="brand-mark">♧</span><div>
<div class="brand-name">TravelMate</div><div class="brand-note">Một chút Đà Lạt, dành riêng cho bạn.</div></div></div>
<div class="hero">
<svg viewBox="0 0 650 320" preserveAspectRatio="xMaxYMax slice" aria-hidden="true">
  <circle cx="487" cy="73" r="35" fill="#f4e8c6"/>
  <path d="M0 230 Q120 90 250 180 T650 130 V320 H0Z" fill="#c3d4bd"/>
  <path d="M0 300 Q170 135 320 230 T650 175 V320 H0Z" fill="#9fb89f"/>
  <path d="M170 320 Q320 210 440 270 T650 215 V320Z" fill="#72977f"/>
  <g fill="#436f5a"><path d="M540 203l-20 36h11l-22 35h24v31h14v-31h24l-22-35h11Z"/>
  <path d="M593 219l-15 27h8l-17 26h18v23h12v-23h18l-17-26h8Z"/>
  <path d="M476 248l-12 22h6l-14 22h17v22h9v-22h17l-14-22h6Z"/></g>
</svg><div class="hero-copy"><div class="eyebrow">Đà Lạt · Cao nguyên & những cuộc hẹn</div>
<h1>Tìm một nơi<br>hợp với bạn.</h1>
<p>Một tách cà phê giữa cây xanh, một bữa ăn có view đẹp, hay một góc nhỏ để khám phá. Kể điều bạn thích, để TravelMate gợi ý.</p>
<span class="hero-pill">Cà phê &nbsp;·&nbsp; Ăn uống &nbsp;·&nbsp; Tham quan</span></div></div>
""", unsafe_allow_html=True)


def safe_url(value: object) -> str | None:
    if isinstance(value, str) and urlparse(value).scheme in ("http", "https"):
        return value
    return None


def render_card(place: dict) -> str:
    name = html.escape(str(place.get("name") or "Địa điểm"))
    photo_url = safe_url(place.get("photo_url"))
    photo = (
        f'<img src="{html.escape(photo_url, quote=True)}" alt="Ảnh {name}" loading="lazy" referrerpolicy="no-referrer">'
        if photo_url else '<span class="photo-placeholder">🌲 Chưa có ảnh địa điểm</span>'
    )
    rating = place.get("rating")
    rating_text = f"★ {rating:g}" if isinstance(rating, (int, float)) and not isinstance(rating, bool) else "Chưa có rating"
    count = place.get("review_count")
    count_text = f" · {count:,} đánh giá" if isinstance(count, int) and not isinstance(count, bool) else ""
    address = html.escape(str(place.get("address") or "Chưa có thông tin địa chỉ"))
    reason = html.escape(str(place.get("reason") or "Chưa có thông tin giải thích.")).replace("\n", "<br>")
    maps_url = safe_url(place.get("google_maps_url"))
    link = f'<a class="maps-link" href="{html.escape(maps_url, quote=True)}" target="_blank" rel="noopener noreferrer">Mở Google Maps ↗</a>' if maps_url else '<span class="address">Chưa có link Google Maps</span>'
    return f'<article class="place-card"><div class="photo">{photo}</div><div class="place-body"><h3 class="place-name">{name}</h3><div class="rating">{rating_text}<span>{count_text}</span></div><p class="address">⌖ {address}</p><div class="reason">{reason}</div>{link}</div></article>'


with st.form("recommendation_form"):
    st.markdown("**Bạn muốn khám phá điều gì?**")
    description = st.text_area(
        "Sở thích của bạn", label_visibility="collapsed", height=110,
        placeholder="Ví dụ: Tôi muốn quán cà phê nhiều cây xanh và nhà hàng đồ nướng có cảnh đẹp…",
    )
    st.caption("📍 Đà Lạt · Bạn có thể tìm nhiều nhu cầu trong cùng một mô tả.")
    with st.expander("Tùy chọn kết quả"):
        left, right = st.columns(2)
        max_candidates = left.number_input("Địa điểm xem xét mỗi nhu cầu", min_value=1, value=10, step=1)
        top_k = right.number_input("Gợi ý hiển thị mỗi nhu cầu", min_value=1, value=2, step=1)
        st.caption("Xem xét nhiều địa điểm sẽ cần thêm thời gian. Kết quả có thể ít hơn số gợi ý bạn chọn.")
    submitted = st.form_submit_button("Tìm nơi dành cho bạn  →", type="primary", use_container_width=True)

if submitted:
    if not description.strip():
        st.warning("Bạn hãy kể một chút về điều mình muốn tìm nhé.")
    else:
        # Chỉ gửi khi submit; đổi tùy chọn hoặc rerun không tự gọi API.
        st.session_state.pop("recommendation_response", None)
        with st.spinner("Đang tìm địa điểm và đọc những trải nghiệm dành cho bạn…"):
            try:
                response = requests.post(
                    BACKEND_URL + "/recommendations",
                    json={"description": description.strip(), "location": "Đà Lạt", "max_candidates_per_group": int(max_candidates), "top_k": int(top_k)},
                    timeout=(10, 300),
                )
                if response.status_code != 200:
                    messages = {
                        422: "Yêu cầu chưa hợp lệ. Hãy kiểm tra mô tả và tùy chọn kết quả.",
                        502: "Dịch vụ tìm kiếm đang gặp sự cố. Bạn thử lại sau nhé.",
                        503: "Backend chưa có đủ cấu hình để chạy. Hãy kiểm tra cấu hình ở máy chủ.",
                    }
                    st.error(messages.get(response.status_code, "Chưa thể lấy kết quả. Bạn thử lại sau nhé."))
                else:
                    data = response.json()
                    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
                        raise ValueError("Invalid response")
                    if any(not isinstance(g, dict) or not isinstance(g.get("places"), list) or any(not isinstance(p, dict) for p in g["places"]) for g in data["groups"]):
                        raise ValueError("Invalid groups")
                    st.session_state["recommendation_response"] = data
            except requests.Timeout:
                st.error("Lần tìm kiếm đang mất nhiều thời gian. Bạn có thể thử lại với ít địa điểm xem xét hơn.")
            except requests.ConnectionError:
                st.error("Chưa kết nối được với backend. Hãy khởi động FastAPI rồi thử lại.")
            except (requests.RequestException, ValueError):
                st.error("Chưa đọc được kết quả từ backend. Bạn thử lại sau nhé.")

data = st.session_state.get("recommendation_response")
if data is not None:
    st.markdown('<div class="section-title">Những nơi để bạn cân nhắc</div><div class="section-note">Gợi ý theo từng nhu cầu · Ảnh và đánh giá từ dữ liệu địa điểm</div>', unsafe_allow_html=True)
    if not data["groups"]:
        st.info("Chưa tìm thấy nhóm địa điểm để gợi ý. Bạn thử mô tả cụ thể hơn nhé.")
    for group in data["groups"]:
        st.subheader(str(group.get("need") or "Gợi ý"))
        if not group["places"]:
            st.info(str(group.get("message") or "Chưa có địa điểm được đánh giá thành công cho nhu cầu này."))
        else:
            st.markdown('<div class="place-grid">' + "".join(render_card(p) for p in group["places"]) + '</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="empty">🌿<br>Mỗi chuyến đi bắt đầu từ một điều bạn thích.<br>Gợi ý của bạn sẽ xuất hiện ở đây.</div>', unsafe_allow_html=True)

st.markdown('<div class="footer">TravelMate · Khám phá Đà Lạt theo cách của bạn.<br>Gợi ý dựa trên thông tin và trải nghiệm được ghi nhận, không bảo đảm mọi sở thích đều được xác minh.</div>', unsafe_allow_html=True)
