# Đánh giá thủ công DaLat TravelMate

## 1. File nào dùng để làm gì?

| File | Vai trò |
|---|---|
| [cases.json](cases.json) | 10 câu E01–E10 đã chốt và kỳ vọng theo ý nghĩa |
| [run.py](run.py) | Chạy graph một lần mỗi câu và lưu dữ liệu để chấm |
| `runs/<run-id>/manifest.json` | Cấu hình, phiên bản code, thời gian và trạng thái thực thi |
| `runs/<run-id>/E01.json` … | Nhu cầu, query, ứng viên, evidence, assessment, output và lỗi |
| `runs/<run-id>/report.md` | Bản đọc dễ hơn của dữ liệu JSON; runner tự tạo, chưa tự chấm |
| `runs/<run-id>/manual_review.md` | Nhận xét chấm riêng của người đọc; chỉ tạo khi thực hiện review |

Hiện đã có một lần chạy thử riêng E02 và một lần chạy đủ 10 câu. Lần đầy đủ có report và manual_review; lần thử E02 chỉ giữ JSON/manifest để tránh nhiều bản trình bày không cần thiết. `manual_review.json` đã được loại vì là bản phụ, không có chương trình nào đọc nó. Các kết quả local trong `runs/` bị Git và Docker build bỏ qua.

`report.md` và `manual_review.md` không trùng vai trò: một file trình bày **bài làm và nguồn**, file còn lại ghi **nhận xét chấm**. Không xóa JSON gốc vì đó là bằng chứng để kiểm tra lại mà không gọi API.

## 2. Hai phần benchmark chính

### Hiểu nhu cầu — chấm theo câu

So description với các nhóm và tiêu chí thực tế: giữ ý chính, đúng nhóm, đúng mong muốn/điều cần tránh. Không yêu cầu tên nhóm, thứ tự hoặc câu chữ giống nguyên văn kỳ vọng. Loại địa điểm có thể nằm trong tên nhóm/query/tiêu chí. Câu chỉ hỏi ăn vặt không được tự thêm giá rẻ, ngon hoặc yên tĩnh.

Theo tiêu chuẩn đã thống nhất, cả 10 câu của lần chạy đầy đủ được người dùng chốt Đạt về hiểu nhu cầu. Lặp biểu diễn hoặc nguy cơ mất quan hệ thời gian được ghi chú kỹ thuật riêng, không tự đổi nhãn cả câu thành hiểu sai.

### Bám nguồn — chấm từng địa điểm, từng tiêu chí

Đọc evidence, ID nguồn hỗ trợ/phản bác, status và explanation cùng nhau:

- `supported`: có nguồn liên quan hỗ trợ đúng tiêu chí.
- `contradicted`: có nguồn liên quan phản bác đúng tiêu chí.
- `mixed`: có cả hai loại; nguồn không nhắc tới không phải phản bác.
- `unknown`: chưa đủ thông tin; có thể là cách xử lý đúng.

Với `avoid`, supported nghĩa là có dấu hiệu điều cần tránh xảy ra. Nhãn loại hình khác không tự phủ định một đặc điểm: quán cà phê vẫn có thể bán ăn vặt. Giữ điều kiện/ngữ cảnh của nguồn và chấp nhận cách diễn đạt tương đương phù hợp ngữ cảnh đã được duyệt.

**Nhãn người chấm:** Đạt / Chưa đạt / Chưa xác định; ô trống nghĩa là chưa chấm. Ghi căn cứ bằng mã câu, nhóm, địa điểm/place_id, tiêu chí và ID nguồn. ID review chỉ có nghĩa trong đúng địa điểm. Chấm cả ứng viên assessed không được chọn Top-K; không dùng rating hoặc điểm ranking làm nhãn chất lượng.

Người chấm Chưa xác định khác Agent trả unknown. Ví dụ không có nguồn về trà, Agent trả unknown có thể được chấm Đạt; điều đó không chứng minh quán không có trà. Những suy luận mơ hồ phải thống nhất trước khi chốt nhãn, không tự sửa kỳ vọng để ép khớp kết quả.

**Ngoài benchmark:** lý do cuối, giữ điều kiện/unknown trên UI và ảnh/link chỉ lưu để tham khảo, không có bảng điểm output. Test logic Python là phần kiểm tra kỹ thuật riêng, không phải nhãn chất lượng LLM.

### Nguyên tắc dùng bộ câu hỏi

Chỉ gửi `description` và `location` cho Agent. `id` nhận diện case; `expected_groups` và `notes` dành cho người chấm, không được gửi vào prompt. Không có tên quán cố định làm đáp án. Hai giới hạn chạy là cấu hình, không nằm trong kỳ vọng.

Bộ nhỏ này phục vụ phát hiện lỗi và so phiên bản trên các tình huống đã chốt; không gọi kết quả là accuracy toàn hệ thống. Review mẫu không đại diện toàn bộ trải nghiệm; có nguồn không có nghĩa đã xác minh ngoài đời.

## 3. Cách chạy

Từ thư mục gốc repo, dùng môi trường đã cài dependencies và `.env` đủ bốn biến API theo [README dự án](../README.md). Không cần bật FastAPI, Streamlit hoặc Docker.

```bash
conda activate dalat-travelmate
```

Chạy một câu trước:

```bash
python -m evaluation.run --case E02 \
  --max-candidates-per-group 3 --top-k 2
```

Chạy cả 10 câu theo thứ tự:

```bash
python -m evaluation.run --all \
  --max-candidates-per-group 3 --top-k 2
```

Phải chọn `--case` hoặc `--all`; hai giới hạn bắt buộc là số nguyên dương. 3/2 là ví dụ; mỗi nhóm xét tối đa 3 ứng viên, trả tối đa 2 đề xuất. Câu nhiều nhóm dùng nhiều lời gọi hơn. **Các lệnh này gọi API thật, có thể tính phí/hạn mức.** Không chạy lại chỉ để đọc kết quả cũ.

Runner không tự retry case hoặc gọi API để bổ sung báo cáo; query rộng và retry mặc định của SDK vẫn theo Agent hiện có. Mỗi lần chạy tạo thư mục UTC + mã ngẫu nhiên riêng, không ghi đè lần trước. Trong một lần chạy, JSON cập nhật sau từng node; manifest và report cập nhật sau từng case.

## 4. Đọc kết quả và lỗi

Đọc `manifest.json` trước, rồi `report.md`, đối chiếu JSON khi cần. Ghi nhận xét vào `manual_review.md` riêng để không lẫn dữ liệu nguồn với nhãn chấm. Khi tự tạo review, không tự điền kết quả thành công trước khi đọc nguồn.

- `pending`: chưa bắt đầu; `running`: đang chạy hoặc bị dừng cưỡng bức.
- `completed`: graph trả đủ dữ liệu, không có issue thực thi ghi nhận; không có nghĩa là chất lượng Đạt.
- `completed_with_issues`: có ứng viên lỗi hoặc nhóm thiếu đề xuất.
- `error`: case lỗi, giữ phần node đã hoàn thành và tiếp tục case kế tiếp.
- `interrupted`: Ctrl+C, giữ phần đã nhận và không chạy các case kế tiếp.

Ứng viên `not_evaluated` do giới hạn/thiếu ID/trùng ID không đồng nghĩa không phù hợp. `missing_fields` là chưa thu được dữ liệu, khác danh sách có mặt nhưng rỗng. Case lỗi không tự là lỗi ngữ nghĩa; ghi riêng phần chưa thể chấm.

Chỉ giữ được dữ liệu **node đã trả ra**, không phải dữ liệu xử lý dở. Details thành công nhưng Reviews lỗi hiện không giữ riêng Details. Evidence xuất là phần chuẩn bị cho LLM, không phải toàn bộ JSON API. Không dump raw Search metadata, biến môi trường hoặc exception thô; secret cấu hình và tham số URL nhạy cảm được redact. Không commit dữ liệu local chưa xem lại.

`recommendation_links` nối output bằng index nhóm, vị trí assessment và place_id theo chính ranking; không dò tên. Index từ 0, rank từ 1. URL trong report là văn bản, không tự mở link/tải ảnh. Có URL chưa chứng minh ảnh/link thật hoạt động.

Manifest ghi model ID, commit và cờ dirty. Nếu dirty=true, commit chưa đủ mô tả code khi chạy. Mã thoát 0/1/130 lần lượt là hoàn thành không issue/có issue/bị ngắt; không phải điểm chất lượng. Lỗi ổ đĩa/quyền ghi có thể dừng chương trình. Chạy lại không resume, sẽ gọi API lại.

## 5. Kiểm tra offline

```bash
python -m unittest discover -s tests -v
```

Test hiện có kiểm tra runner bằng thư mục tạm, graph giả và graph thực với các dịch vụ đã mock; kết nối socket bị chặn. Kiểm tra mapping, một stream mỗi case, dữ liệu trước lỗi, ngắt, redaction và không ghi đè. Test ranking/assessment validation riêng chưa bổ sung; test runner không chứng minh LLM phân tích đúng.
