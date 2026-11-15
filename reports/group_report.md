# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`out/*/run_info.json`, `out/poc/release_diffs.json`, `reports/metrics_*.json`) — không gõ tay.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| MSSV | 2A202603152 |
| Họ và tên | ĐINH QUANG THẮNG |
| Group ID | G00 |
| Challenge | T06 · Dataset Semantic Integrity & Provenance Gate |
| Thành viên (5–6) + vai trò | Điền tên thật vào `reports/team_contributions.csv` + Bảng 2 (mục 10) khi chốt nhóm: 1. ____ (Lead/Integrator) · 2. ____ (Data & fixtures) · 3. ____ (Core algorithm) · 4. ____ (QA/metric) · 5. ____ (Review + report) · 6. ____ |
| Git URL | https://github.com/quangthang311/K5-L2A-DAY06-DinhQuangThang-2A202603152-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | ____ (chạy `make tag-demo` khi freeze demo) |
| Tag `final-24h` (commit) | ____ (chạy `make tag-final` khi nộp) |
| Deadline (giờ VN) | ____ |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?** 
=> Người dùng dataset và nhóm huấn luyện model: một release dataset "hỏng im lặng" (JSON vẫn parse được nhưng class map đã đảo, frame đã rơi, ID đã trùng, bbox đã lệch, label map cũ) sẽ vào thẳng train set → model học sai nhãn/học thiếu dữ liệu mà không có lỗi nào hiển thị. Vendor bị thiệt ngược lại nếu gate chặn oan release lành tính (false block → rework tốn tiền).
- **Điểm nghẽn cụ thể:** 
=> Mỗi tuần vendor nộp 20 release ứng viên trên cùng 1 parent release; "JSON hợp lệ + file tồn tại" là điều kiện hiển nhiên của mọi release nên không bắt được gì (đo thật: baseline parse+file-exists chặn **0/20**). "Có diff so với parent" cũng không phải tín hiệu vì **mọi release đều có thay đổi lành tính** (jitter bbox ≤ 1.00 px, vendor thêm frame mới, đổi thứ tự annotation) — phải kiểm *invariant ngữ nghĩa* mới tách được lỗi thật.
- **Đầu vào → đầu ra:** 
=> `fixtures/t06_release_gate/` (parent `releases/v1.0`: COCO 100 ảnh / 697 annotation / 5 class + `classes.txt` + 100 file YOLO; `releases/label_maps.json` (lm-2, lm-3); 20 release ứng viên r01–r20; `releases.csv`; `manifest.csv` 245 file) → `out/release_decisions.csv` (`release_id`, `decision` ∈ {PASS, HOLD, REWORK} + `root_cause` ∈ {class_swap, bbox_shift, id_collision, dropped_frames, stale_map, clean}) + `review_queue.csv` top-B + contact sheet + `release_diffs.json` (bằng chứng từng release) + `decision.json` của batch.
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):** 
=> *per release* — vi phạm 0 họ invariant → **PASS**; 1 họ → **HOLD** (cần người ký duyệt); ≥ 2 họ cùng lúc → **REWORK** (hỏng hệ thống). *Batch* — block rate ≥ 0.30 → **REWORK**, > 0 → **HOLD**, = 0 → **GO** (ngưỡng frozen trong `configs/lab.yaml`). Mọi decision bắt buộc `reason_code` + `owner` (QA Lead — Group G00). Đơn vị chấm metric là **release**, decision của batch là `Decision` object riêng (decision.json).
- **Giả định của nhóm (cần DPO/legal/domain owner xác nhận):** 
=> parent release `v1.0` được coi là "chuẩn vàng kỹ thuật" (đã verify manifest sha256 + round-trip COCO↔YOLO 0 lỗi) — nếu parent本身 lỗi thì mọi so sánh lệch; "thay đổi lành tính" (jitter ≤ 1 px, thêm frame mới có ID/annotation riêng, reorder annotation) phải do data-team xác nhận theo quy ước vendor thực tế. Fixture synthetic CC0, không PII; pipeline chỉ là gate kỹ thuật, không phải xác nhận pháp lý.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev (r01–r10) | 10 release | `fixtures/t06_release_gate/` — sinh bởi `tools/make_fixtures.py` (giảng viên, seed 42) | CC0-1.0 (synthetic) | Có |
| eval / heldout (r11–r20) | 10 release | cùng nguồn, tách theo `split` trong `releases.csv` — nhóm không dùng eval để tune | CC0-1.0 (synthetic) | Có |

- **Schema & class mapping:** 
=> parent COCO (`info/images/annotations/categories`, 5 class car/pedestrian/motorbike/sign/truck) + `classes.txt` (thứ tự YOLO 0–4) + `releases/label_maps.json` lịch sử map (`lm-2` 4 class, `lm-3` 5 class); mỗi release ứng viên khai `label_map_version` trong `release_meta.json` kèm `parent_sha256`. GT ẩn (chỉ giảng viên): `gt/gt_releases.csv: is_defective, corruption_type`.
- **Seed:** 42 cho mọi run (ghi trong `run_info.json`); pipeline **không dùng random** — output byte-identical khi chạy lại (đã verify bằng `cmp`).
- **`manifest.csv` verified (sha256):** có — 245 file (100 ảnh `images/`, 103 artefact parent `releases/v1.0/`, 41 file candidates + label_maps): **0 problem** qua `verify_manifest` (chạy ở bước 01 của cả PoC lẫn baseline; `python -m tools.verify_manifests` nếu máy có tools/).
- **Dữ liệu thật dùng (nếu có):** chưa dùng (`data/real/coco/` chưa được giảng viên cấp). Nếu dùng: tự inject 5 loại corruption vào `annotations_subset.json` COCO thật rồi cho gate chạy lại — protocol giống fixture, không commit PII.

## 03 · Research & design

- **References:**
  1. Great Expectations Core 1.x (ValidationDefinition/Checkpoint — handout Day06, xem 2026-11-14): mô hình "expectation/invariant" khai báo trước, validation chạy định kỳ → động lực cho việc liệt kê invariant tách bạch từng họ lỗi (mỗi violation có family + detail riêng).
  2. DVC (https://dvc.org/, xem 2026-11-14): provenance theo hash — mọi release phải pin đúng `parent_sha256`; hash sai = provenance gãy, chặn ngay bước load.
  3. Datumaro (https://github.com/openvinotoolkit/datumaro, xem 2026-11-14): kiểm tra tính nhất quán dataset ngữ nghĩa (category set, bbox trong ảnh, frame liên tục) khi convert giữa COCO↔YOLO.
- **Sơ đồ data flow:** `load()` (verify 245 hash manifest + `releases.csv` + parent artefacts + **round-trip COCO↔YOLO trên parent: 0 mismatch**) → `process()` (integrity gate từng release — 8 họ invariant, xem Bảng A) → `rank()` (top-B=12 theo score giảm dần, reason = bằng chứng cụ thể) → `review()` (override từ `review_queue_reviewed.csv`, `apply_overrides`, AuditLog JSONL append-only) → `decide()` (per-release PASS/HOLD/REWORK đã ghi ở bước 02/04; batch GO/HOLD/REWORK theo block-rate policy frozen) → `release_diffs.json` (full evidence để reviewer đối chiếu).
- **Thành phần offline:** 100% stdlib + pandas/Pillow (chỉ dùng cho contact sheet), không model pretrained, không network (`--offline` + offline guard). Chạy 2 lần cùng seed 42 → `release_decisions.csv` **byte-identical** (verify bằng `cmp`).
- **Trade-offs đã cân nhắc:**
  - So sánh với parent theo **annotation id** — khi ID trùng (id_collision) thì join theo ID bất khả tín, nên gate **tự triệt tiêu** các kiểm tra id-join (bbox shift / relabel) cho release đó và chỉ báo id_collision → tránh đếm đôi cùng một lỗi thành 2 họ (sẽ falsely REWORK).
  - "Thêm frame mới" (r03-style: `seq_extra` nhân bản frame_000 kèm 1 annotation mới) chỉ là **cảnh báo** cho reviewer, không tự chặn — vì không có căn cứ ngữ nghĩa nói đó là lỗi; đây chính là "có diff ≠ lỗi".
  - `bbox_shift` dùng **tỷ lệ** annotation lệch (≥ 5%) chứ không đếm tuyệt đối — release lớn lệch 2 bbox vẫn là nhiễu; ngưỡng px chọn từ đo đạc dev (jitter ≤ 1.00 px vs corrupt ≥ 7.89 px).
  - Root cause chọn theo **thứ tự ưu tiên frozen** (class_swap > stale_map > id_collision > dropped_frames > bbox_shift > …) khi một release vi phạm nhiều họ — vì primary metric phụ có Root-cause accuracy nên thứ tự này phải cố định trước khi eval.

**Bảng A · 8 invariant kiểm tra ở bước 02 (đều không cần nhãn)**

| Họ lỗi (root_cause) | Bằng chứng kiểm tra gì | Chặn? |
|---|---|---|
| class_swap | `categories` đảo tên giữa các id so với map đã khai báo (`label_maps[lm-3]`) / annotation bị relabel so với parent | Có |
| stale_map | `categories` thiếu/thừa class so với map khai báo; annotation tham chiếu `category_id` không có trong `categories` | Có |
| id_collision | `image_id` / `annotation_id` trùng nhau trong release; (2 image id cùng trỏ 1 file chỉ là cảnh báo) | Có |
| dropped_frames | `frame_index` hụt trong từng `sequence_id`; ảnh của parent biến mất khỏi candidate | Có |
| bbox_shift | ≥ 5% annotation dịch > 5 px so với parent (join theo id); bbox nhảy ra ngoài ảnh | Có |
| provenance | `release_meta.parent_sha256` ≠ sha256 thật của parent `annotations.json` | Có |
| schema | JSON không parse được / thiếu key COCO / file ảnh được trỏ tới không tồn tại | Có |
| dangling_reference | annotation tham chiếu `image_id` không có trong release | Có |

## 04 · Baseline vs PoC

- **Baseline** (`src/baseline.py`, đúng định nghĩa handout T06 §4): chỉ **parse JSON/schema + kiểm file tồn tại** — annotations.json/release_meta.json parse được, đủ 4 key COCO, mọi `file_name` tồn tại trên đĩa; **không so semantic invariant**. Kết quả trên fixture: **0/20 bị chặn** (mọi JSON đều hợp lệ, mọi file tồn tại) → Silent-defect Detection F1 của baseline sẽ là **0** nếu GT khớp phân tích của nhóm; nhóm báo thẳng "baseline = 0" thay vì phần trăm.
- **PoC** (`src/pipeline.py`, params frozen trong `configs/lab.yaml`): integrity gate 8 họ invariant (Bảng A) so với parent + label map khai báo; chi tiết ở mục 03.
- **Cùng pool / cùng budget / cùng seed:** xác nhận — cả hai chạy `--seed 42`, cùng 20 release, cùng B=12 review queue, cùng contact sheet + audit log; cùng eval split để giảng viên chấm.

**Bảng 1 · Baseline vs PoC (phần nhóm tự đo được không cần GT — nguồn: `out/*/run_info.json` + `release_diffs.json`)**

> ⚠️ `reports/metrics_baseline.json`, `reports/metrics_poc.json`, `reports/table1_baseline_vs_poc.md` **chưa sinh được** trên repo học viên vì `gt/gt_releases.csv` chỉ có ở overlay giảng viên (`make eval-baseline eval-poc compare` → exit 2). Giảng viên chạy lệnh khi cài overlay; nhóm **không điền tay** các file này.

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Số release bị chặn / 20 (block rate) | 0 (0.00) | 10 (0.50) | baseline không có invariant nào để chặn; higher block rate ≠ tốt hơn — False-block rate là secondary |
| Họ lỗi được phát hiện (count) | 0 (chỉ lỗi parse/file — fixture không có) | class_swap 2 · stale_map 2 · id_collision 2 · dropped_frames 2 · bbox_shift 2 | baseline = 0 trên cả 5 họ lỗi im lặng |
| Silent-defect Detection F1 | **đợi overlay giảng viên** (kỳ vọng nhóm: 0) | **đợi overlay giảng viên** | lệnh: `make eval-baseline eval-poc compare TRACK=t06` |
| False-block rate (release sạch bị chặn) | 0 | 0/10 dev-clean tự kiểm (r03, r04, r06 PASS dù có diff lành tính) | chính là điểm nghẽn "có diff ≠ lỗi" |
| Runtime / 100 release | 0.2617 s / 20 ≈ **1.31 s / 100** | 0.3957 s / 20 ≈ **1.98 s / 100** | gồm verify 245 hash sha256; CPU Intel x64 Model 154, Python 3.11.9, Windows |

## 05 · Evaluation protocol

- **Công thức primary metric:** `Silent-defect Detection F1` = F1 của việc chặn release lỗi, đơn vị = release, positive = defective & blocked; tính trên split **eval** (r11–r20) qua `src/metrics/tracks.py::eval_t06`. Secondary: False-block rate trên release sạch; Root-cause accuracy (khớp `root_cause` ↔ `corruption_type`); runtime/100 release. Chi tiết đầy đủ: `reports/metric_contract.md`.
- **Threshold / budget B / K và lúc chốt:** B=12 (`configs/lab.yaml`); `shift_tol_px: 5.0`, `min_shift_frac: 0.05`, `rework_min_families: 2`, batch `go_max_block_rate: 0.0` / `rework_min_block_rate: 0.30` — chốt 2026-11-14, trước khi nhìn kết quả eval nào, dựa trên thống kê dev (jitter ≤ 1.00 px / corrupt ≥ 7.89 px).
- **Độ bất định khi N nhỏ:** eval chỉ 10 release → luôn kèm số tuyệt đối (x/10); 1 release chặn sai = ±0.1; không nói % cải thiện khi hiệu số 1–2 release; root-cause accuracy trên eval tối đa 3 release lỗi (theo phân tích nhóm) → mỗi root cause sai là −1/3.
- **Lệnh evaluate chính xác:**
  ```bash
  python -m src.evaluate --track t06 --pred out/baseline/release_decisions.csv --run-name baseline --out reports/metrics_baseline.json
  python -m src.evaluate --track t06 --pred out/poc/release_decisions.csv      --run-name poc      --out reports/metrics_poc.json
  python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
  ```

## 06 · Result slices

Số nhóm tự đo được (không cần GT), từ `out/poc/release_decisions.csv` + `release_diffs.json` (seed 42):

| Slice | N | PoC chặn | Ghi chú |
|---|---|---|---|
| split=dev | 10 | 7 (r01, r02, r05, r07, r08, r09, r10) | 3 PASS r03/r04/r06 — chỉ có diff lành tính (jitter ≤ 1.00 px + 1 frame thêm) |
| split=eval | 10 | 3 (r16, r18, r20) | 7 PASS — trong đó r11/r15/r19 có frame thêm của vendor → chỉ vào review queue (score 0.25), không tự chặn |
| root_cause=class_swap | 2 | r07, r20 | `categories` đảo car↔pedestrian so với lm-3 đã khai báo |
| root_cause=stale_map | 2 | r01, r09 | khai báo lm-3 nhưng ship categories 4 class (lm-2); 44 annotation tham chiếu category_id 5 không tồn tại |
| root_cause=bbox_shift | 2 | r05, r10 | 210/697 annotation dịch > 5 px (max 29.85 px) trong khi jitter lành tính ≤ 1.00 px |
| root_cause=id_collision | 2 | r08, r18 | 12 / 11 duplicate annotation id; id-join bị triệt tiêu để không đếm đôi |
| root_cause=dropped_frames | 2 | r02, r16 | 9 / 7 ảnh parent biến mất (63 annotation rơi theo) + frame_index hụt trong seq3 / seq1 |

- **Failure case 1 (failure mode bắt buộc của handout — "JSON hợp lệ nhưng class mapping đã đảo"):** `r07`/`r20` — JSON parse được, đủ 4 key, 697 annotation, mọi file tồn tại; nhưng `categories` khai `{1: pedestrian, 2: car}` trong khi map đã khai báo lm-3 là `{1: car, 2: pedestrian}` → toàn bộ annotation vẫn trỏ đúng id số, **nhãn ngữ nghĩa đã đảo** (mọi annotation "car" thành "pedestrian" và ngược lại). Baseline (parse + file tồn tại) **bỏ qua**; PoC chặn vì so `categories` với `label_maps[lm-3]` cùng name set nhưng khác assignment → `class_swap`, kèm diff `{1: {declared: car, shipped: pedestrian}, …}` in thẳng vào reason.
- **Failure case 2 (failure mode bắt buộc — "check chỉ khớp size file nên lọt bug"):** so kích thước file là check giả tạo: `r07` lệch **+1 byte** so với parent, `r20`/`r12`/`r13` lệch **0 byte**, `r05` (bbox_shift) chỉ **+61 byte**, `r08` (id_collision) **−1 byte** — chỉ `dropped_frames` mới lộ qua size (−7306 / −5696 byte). Tức là một gate "khớp size/exists" chặn đúng 0/10 release lỗi và 0/10 release sạch trên fixture này; PoC dùng so sánh cấu trúc + nội dung (hash provenance, category map, bbox, frame continuity) nên không phụ thuộc size.
- **Failure case 3 (tự tìm thêm — "có diff không phải tín hiệu"):** 6/20 release (r03, r04, r06, r11, r15, r19) có ảnh mới `seq_extra` trỏ tới file `images/frame_000.jpg` đã tồn tại (duplicate file entry) — nhìn như "trùng lặp" nhưng id mới (101), annotation mới (100002), không vi phạm invariant nào → gate chỉ **cảnh báo** (score 0.25, vào review queue) và PASS. Ngược lại `r08`/`r18` cũng duplicate file entry nhưng kèm 12/11 trùng annotation id → chặn `id_collision`. Phân biệt này chỉ làm được khi invariant tách bạch từng họ.
- **Latency / compute (máy, CPU, ms/release):** PoC ≈ 19.8 ms/release (0.3957 s / 20, gồm verify 245 hash sha256 + round-trip COCO↔YOLO trên parent), Intel x64 Family 6 Model 154, Python 3.11.9, Windows-10-10.0.26200 — ghi trong `run_info.json`.

## 07 · Human & decision

- **Review queue:** `out/poc/review_queue.csv` — top-B=12 theo `score` giảm dần (10 release bị chặn + 2 release cảnh báo cao nhất), cột `reason` = bằng chứng cụ thể (map đảo từng class, số annotation lệch px, list id trùng, gap frame…), `slice` = split dev/eval, `suggested_action` = PASS/HOLD/REWORK; kèm **contact sheet offline** `out/poc/contact_sheet.html` (thẻ metadata từng release, dropdown quyết định, nút Export CSV — không cần ảnh vì evidence là metadata JSON); **`release_diffs.json`** lưu full evidence (violations + warnings + số liệu) cho từng release.
- **Cách override + audit log:** reviewer điền `reviewer`, `reviewer_decision` (approve/reject/edit/escalate/skip), `override_value` ∈ {PASS, HOLD, REWORK} (giá trị khác → pipeline fail rõ ràng), `review_note` rồi lưu thành `out/poc/review_queue_reviewed.csv`; chạy lại `make run` → `review()` đọc file (thiếu reviewer → fail), `apply_overrides` ghi đè `decision`, mỗi thay đổi append 1 dòng JSONL vào `out/audit_log.jsonl` (actor/action/before/after/reason, append-only). Test: `tests/test_pipeline_t06.py::test_t06_review_override_changes_decision_and_audits`.
- **Decision policy + `reason_code` + owner:** per release PASS/HOLD/REWORK (REWORK khi ≥ 2 họ lỗi); batch: block rate 0.50 ≥ 0.30 → **REWORK** (`SEMANTIC_VIOLATIONS_BLOCK_RATE`, metrics: block_rate 0.5, n_blocked 10) với evidence là `release_decisions.csv` + `release_diffs.json`. Owner = `QA Lead — Group G00` (config `owner`). Run hiện tại: `out/poc/decision.json`.
- **Khi nào HOLD/REWORK thay vì tự động PASS:** mọi release vi phạm ≥ 1 invariant là HOLD tối thiểu — PASS chỉ khi 0 violation; reviewer muốn PASS lại release bị chặn phải override có tên + note (bị audit); batch chỉ GO khi block rate = 0.

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/t06_release_gate --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42
# baseline:
python -m src.main --track t06 --pipeline src.baseline --output out/baseline --run-name baseline --offline --seed 42
python -m src.evaluate --track t06 --pred out/poc/release_decisions.csv --out reports/metrics_poc.json   # cần overlay gt/
pytest -q
```

- **Output của `pytest -q`:** **58 passed, 39 skipped** (39 skip = test cần `gt/` của overlay giảng viên; `pytest.skip` theo conftest). Nhóm thêm 11 test mới trong `tests/test_pipeline_t06.py` (E2E PoC + baseline, chặn đúng 10 lỗi planted + root cause, PoC vượt baseline, determinism, rank thiếu `score`, reviewed-file sai giá trị, override + audit, evaluator với duplicate/missing release_id, unit 5 họ invariant) và viết lại `tests/test_cli.py` cho t06 (poc exit 0, stub exit 3, baseline reproducible, GT guard raise trên `gt/gt_releases.csv` dù file không tồn tại, track infer từ folder).
- **Máy / CPU / OS / Python:** Windows-10-10.0.26200 · Intel x64 Model 154 · Python 3.11.9.
- **Lưu ý Windows:** máy làm việc không có `make` trên PATH; chạy trực tiếp `PY=<venv>/Scripts/python.exe; "$PY" -m src.main ...` / `-m pytest` như trên — cả hai exit 0. Chạy PoC 2 lần cùng seed 42 → `release_decisions.csv` byte-identical (verify bằng `cmp`).

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:** fixture synthetic CC0 — an toàn. Nếu chạy trên COCO thật (`data/real/`) phải để gitignored, không commit ảnh có người/biển số; gate này chỉ kiểm metadata nên rủi ro PII nằm ở bước cấp dữ liệu, không phải pipeline — **không** tuyên bố tuân thủ GDPR/luật VN từ gate này.
- **Điều chưa biết; false alarms; scale 10×:** Recall/Precision/F1 thật chưa đo được không có GT — phân tích "10 lỗi / 10 sạch" là **phân tích nhóm trên dev + suy luận cấu trúc**, không phải GT; có thể nhóm nhầm 1 release (ví dụ nếu GT coi `seq_extra` duplicate frame là lỗi thì r03-style sẽ thành false negative của PoC). Root-cause priority frozen có thể sai nếu một release lỗi thuộc 2 họ cùng lúc. Scale 10× (200 release): runtime ~0.2 s — verify 245 hash là phần đắt nhất; parent diff O(n_ann) ổn. Nếu vendor đổi format `file_name` (sub-folder) cần nới `file-exists` theo root manifest.
- **Giả định cần data-team xác nhận:** (1) parent v1.0 là chuẩn vàng (nếu parent lỗi toàn bộ so sánh vô nghĩa — hiện round-trip YOLO↔COCO 0 mismatch + manifest 0 problem); (2) jitter ≤ 1 px và "thêm frame mới có id riêng" là thay đổi lành tính được phép; (3) root-cause priority class_swap > stale_map khi cả hai cùng vi phạm.
- **Kế hoạch cải tiến:** (1) CLI `validate_release` xuất JSON máy đọc được cho 1 release (mốc 180 phút của handout) — hiện `release_diffs.json` đã gần đáp ứng; (2) round-trip COCO↔YOLO cho cả candidate (hiện chỉ parent có yolo_labels); (3) so phân bố class/bbox vs parent (KS-test) bắt drift Gradual mà không cần threshold cứng; (4) bonus Croissant 1.1 metadata cạnh manifest.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

> Điền tên/email thật sau khi mọi thành viên commit; quy tắc rubric: mỗi người ≥1 commit thực chất (commit chỉ đổi khoảng trắng không tính).

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Member 1 | (điền) | Integration / CLI · wiring config | | |
| Member 2 | (điền) | Data + GT protocol · fixtures/provenance | | |
| Member 3 | (điền) | Core algorithm (`src/pipeline.py`, `src/baseline.py`) | | |
| Member 4 | (điền) | Metric + tests (`tests/test_pipeline_t06.py`, `tests/test_cli.py`) | | |
| Member 5 | (điền) | Review queue + report + contact sheet | | |
| Member 6 (nếu có) | (điền) | Research / ablation / debate | | |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| Great Expectations Core 1.x (ValidationDefinition / Checkpoint — tài liệu trong Research Shelf của handout) | 2026-11-14 | Mô hình khai báo expectation/invariant rồi validate theo checkpoint — khuôn mẫu cho 8 họ invariant của gate. Lưu ý 1.x đã bỏ CLI, chỉ dùng API Python. |
| https://dvc.org/ (DVC) | 2026-11-14 | Provenance theo hash nội dung —Release phải pin đúng hash của parent, hash lệch = chặn. |
| https://github.com/openvinotoolkit/datumaro (Datumaro) | 2026-11-14 | Kiểm nhất quán ngữ nghĩa dataset (category set, bbox trong ảnh, convert COCO↔YOLO) trước khi publish. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo trong README; input mẫu không chứa PII thật (synthetic CC0).
- [x] Đúng 1 lệnh run (`python -m src.main ...` exit 0), 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy (offline guard, không model ngoài).
- [x] Có baseline/PoC outputs + 3 failure cases phân tích bằng metadata (r07/r20 class map đảo; size-file check lọt bug; "có diff ≠ lỗi") + reviewer evidence (review queue, contact sheet, release_diffs.json) + decision log.
- [x] Có license/source provenance (manifest 245 file sha256 verified 0 problem), data splits, seed 42, offline environment, eval N=10 release ghi rõ trong metric contract.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên (cần tên/email thật của nhóm).
