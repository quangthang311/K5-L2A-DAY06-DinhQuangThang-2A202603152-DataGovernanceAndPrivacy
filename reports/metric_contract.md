# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T06 · Semantic Integrity & Provenance Gate (`fixtures/t06_release_gate/`) |
| Primary metric (tên đúng như evaluator in ra) | **Silent-defect Detection F1** (đơn vị = release; positive = release lỗi bị chặn; cài sẵn trong `src/metrics/tracks.py::eval_t06`) |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | **release** (20 release ứng viên: 10 dev / 10 eval; chỉ split **eval** được chấm) |
| Công thức + numerator / denominator | F1 = 2·Precision·Recall/(Precision+Recall) với blocked = `decision != GO` (qua `canonical_status`: PASS→GO, HOLD/REWORK bị tính là blocked); TP = release lỗi thật (`is_defective=1`) bị chặn, FN = release lỗi không bị chặn (thiếu dòng trong predictions → merge left + fillna "GO" → tính là không chặn), FP = release sạch bị chặn (nếu bị chặn thì Primary không còn ý nghĩa) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | join theo `release_id`; mỗi release đúng 1 dòng (evaluator raises nếu trùng `release_id`); `decision` đổi chữ hoa/thường qua `canonical_status` |
| Candidate pool cố định | toàn bộ 20 release trong `fixtures/t06_release_gate/releases.csv` (r01–r10 dev, r11–r20 eval) |
| Review budget B / K | **B = 12** release vào review queue (`configs/lab.yaml` `params.budget`, không đổi giữa baseline và PoC) |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Không dùng nhãn. Mọi so sánh chỉ làm với **parent release** `releases/v1.0` (input) và `releases/label_maps.json` (input). Ngưỡng chọn từ thống kê split **dev** (r01–r10): jitter bbox lành tính của vendor đo được tối đa **1.00 px**, corrupt shift nhỏ nhất **7.89 px** → `shift_tol_px: 5.0` nằm giữa hai cụm; `min_shift_frac: 0.05` (≥ 5% annotation lệch mới tính là bbox_shift); policy per-release `rework_min_families: 2`, batch `go_max_block_rate: 0.0` / `rework_min_block_rate: 0.30`. Frozen trong `configs/lab.yaml` trước khi chạy eval. |
| Eval split (không dùng để tune) | split **eval** (r11–r20) — chỉ giảng viên chấm qua `src.evaluate` |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | **False-block rate** = release sạch bị chặn / release sạch (secondary, `eval_t06` in sẵn) — chặn oan release lành tính làm vendor phải rework tốn kém; thiếu release lỗi (silent defect lọt) là failure xấu nhất của gate này |
| Slices sẽ báo cáo (≥2) | (1) `corruption_type` (class_swap / bbox_shift / id_collision / dropped_frames / stale_map / clean — bảng block rate theo loại); (2) `split` dev (tự kiểm của nhóm, có tự phân tích) vs eval (giảng viên chấm); (3) cảnh báo không chặn (`duplicate_file_entry` / `added_frames`) — "có diff" không phải tín hiệu lỗi |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Eval chỉ có 10 release → **luôn báo kèm số tuyệt đối (x/10)** chứ không chỉ %; 1 release sai = ±0.1 trên mọi rate; không nói "% cải thiện" khi hiệu số chỉ 1–2 release |
| Ngày giờ chốt + người chốt | 2026-11-14 · QA Lead — Group G00 (trước khi nhìn bất kỳ kết quả eval nào; repo học viên không có `gt/`) |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

**Lưu ý trung thực:** do `gt/gt_releases.csv` chỉ có ở overlay giảng viên, nhóm không tự tính được Silent-defect Detection F1 trước khi nộp.
Mọi con số nhóm tự đo được (không cần nhãn) đều xuất phát từ `out/*/run_info.json` + `out/poc/release_diffs.json` do script sinh ra:
số release bị chặn (10/20), root cause từng release, block rate theo họ lỗi, cảnh báo không chặn (6 release có frame thêm của vendor), và runtime.
F1 / False-block rate / Root-cause accuracy sẽ do giảng viên chạy `src.evaluate` và đối chiếu — nhóm không chỉnh file metrics tay.
Baseline của nhóm (parse + file-exists) chặn 0/20 trên fixture (mọi JSON đều parse được, mọi file tồn tại) — nếu GT khớp phân tích của nhóm thì **baseline = 0**, nhóm ghi rõ chứ không tính phần trăm cải thiện.
