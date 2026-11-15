# Demo script — T06 Semantic Integrity & Provenance Gate (Group G00, 3–5 phút)

## Chuẩn bị trước (offline, không download gì)
```bash
python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42
python -m src.main --track t06 --pipeline src.baseline --output out/baseline --run-name baseline --offline --seed 42
```

## 1. Vấn đề (30 giây)
- Release dataset hỏng *im lặng*: JSON vẫn parse được nhưng class map đã đảo, frame đã rơi, ID đã trùng, bbox đã lệch, label map cũ — không có error nào để bắt.
- Baseline handout = "parse JSON/schema + file tồn tại" → trên fixture chặn **0/20** (mọi release đều hợp lệ về parse).
- "Có diff so với parent" cũng không phải tín hiệu: mọi release đều có thay đổi lành tính (jitter bbox ≤ 1.00 px, vendor thêm frame mới).

## 2. Chạy live (1 lệnh, <1 giây)
```bash
python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42
```
Chỉ ra: exit 0, `out/poc/release_decisions.csv` (release_id, decision, root_cause), `run_info.json`
(seed 42, runtime ~0.4 s, n_blocked=10), `decision.json` (REWORK, reason_code SEMANTIC_VIOLATIONS_BLOCK_RATE, owner).

## 3. Kết quả gate (1 phút) — 10/20 bị chặn, mỗi lỗi 1 root cause
| Root cause | Release | Bằng chứng (in thẳng trong `reason`) |
|---|---|---|
| class_swap | r07, r20 | `{1: {declared: car, shipped: pedestrian}, 2: {...}}` — map lm-3 bị đảo car↔pedestrian |
| stale_map | r01, r09 | khai lm-3 nhưng ship categories 4 class; 44 annotation trỏ category_id 5 không tồn tại |
| bbox_shift | r05, r10 | 210/697 annotation dịch > 5 px (max 29.85 px) trong khi jitter lành tính ≤ 1.00 px |
| id_collision | r08, r18 | 12 / 11 duplicate annotation id (id-join tự triệt tiêu để không đếm đôi) |
| dropped_frames | r02, r16 | 9 / 7 ảnh parent biến mất (63 annotation rơi theo) + frame_index hụt seq3/seq1 |

10 release sạch PASS dù có diff (r03-style: frame `seq_extra` nhân bản frame_000 → chỉ **cảnh báo** vào review queue, không tự chặn) → "có diff ≠ lỗi".

## 4. Contact sheet — human-in-the-loop (1 phút)
Mở `out/poc/contact_sheet.html` bằng trình duyệt (offline, thẻ metadata từng release + reason):
- 12 release ưu tiên (10 bị chặn + 2 cảnh báo) + bằng chứng cụ thể.
- Nhập tên reviewer → chọn quyết định cho 1 release (ví dụ `edit` → `PASS`) → Export CSV →
  lưu thành `out/poc/review_queue_reviewed.csv` → chạy lại lệnh trên → chỉ ra
  `audit_log.jsonl` có thêm dòng `override:edit` (append-only, ai/sửa gì/lý do).

## 5. 2 failure mode bắt buộc của handout — minh hoạ trên fixture (1 phút)
| Failure mode | Minh hoạ | Metadata |
|---|---|---|
| JSON hợp lệ nhưng class mapping đã đảo | `r07`/`r20` — parse OK, 697 annotation, mọi file tồn tại, nhưng car↔pedestrian đã hoán đổi | gate so `categories` với `label_maps[lm-3]` (cùng name set, khác assignment) |
| Check chỉ khớp size file nên lọt bug | `r07` lệch **+1 byte**, `r20` **0 byte**, `r05` **+61 byte**, `r08` **−1 byte** so với parent → size-only check chặn 0/10 lỗi | gate dùng hash provenance + so cấu trúc, không dùng size |

## 6. Reproducibility + tests (30 giây)
```bash
pytest -q   # 58 passed, 39 skipped (skip = cần overlay gt/ giảng viên)
```
- Chạy 2 lần cùng seed 42 → `release_decisions.csv` byte-identical (đã `cmp`).
- Guards: `--offline` chặn network (exit 4), GT guard chặn đọc `gt/` (exit 5).

## 7. Kết quả + điều trung thực (30 giây)
- PoC chặn 10/20 (block rate 0.50) với root cause đúng 5 họ lỗi; baseline chặn 0/20 — **baseline = 0**.
- Silent-defect Detection F1 / False-block rate / Root-cause accuracy **chưa tự chấm được** vì `gt/gt_releases.csv`
  ở overlay giảng viên — số cuối do `python -m src.evaluate` quyết định; nhóm không chỉnh file metrics tay.
- Decision batch hiện tại: REWORK (block rate 0.50 ≥ 0.30) — cả lô release cần soát lại trước khi publish;
  chi tiết per-release nằm trong `release_decisions.csv` + bằng chứng trong `release_diffs.json`.
