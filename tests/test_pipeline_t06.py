"""Group tests — T06 pipeline (src/pipeline.py, src/baseline.py).

Success path: full 5-step run on the real t06 fixture (PoC + baseline).
Sanity: every release with a planted silent corruption is blocked with the
right root cause, and clean releases (vendor jitter / added frames only) PASS.
Failure/edge: rank() without a `score` column; invalid reviewed-file rows;
              invalid override_value; duplicate release_id / missing rows in
              release_decisions.csv must hurt or fail the evaluator loudly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.baseline import run as run_baseline
from src.common.context import RunContext
from src.common.io import set_seed
from src.common.review import AuditLog, load_review_decisions
from src.metrics.tracks import TRACKS
from src.pipeline import check_release, load, process, rank, review, run as run_poc

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "fixtures" / "t06_release_gate"
OWNER = "QA Lead — Group G00"
SPEC = TRACKS["t06"]

# Planted silent corruptions found by diffing candidates against the parent on the DEV split
# (no gt/ involved — the same families we expect the gate to catch on eval).
DEV_DEFECTS = {
    "r01": "stale_map", "r02": "dropped_frames", "r05": "bbox_shift", "r07": "class_swap",
    "r08": "id_collision", "r09": "stale_map", "r10": "bbox_shift",
}
DEV_CLEAN = ["r03", "r04", "r06"]
EVAL_DEFECTS = {"r16": "dropped_frames", "r18": "id_collision", "r20": "class_swap"}
EVAL_CLEAN = ["r11", "r12", "r13", "r14", "r15", "r17", "r19"]


def make_ctx(tmp_path: Path, out_name: str = "out", pipeline_cfg: dict | None = None) -> RunContext:
    cfg = {"track": "t06", "owner": OWNER, "group_id": "G00", "strict_provenance": True,
           "params": {} if pipeline_cfg is None else pipeline_cfg}
    return RunContext(track="t06", input_dir=FX, output_dir=tmp_path / out_name, config=cfg,
                      seed=42, rng=set_seed(42), run_name="test", offline=True,
                      audit=AuditLog(tmp_path / out_name / "audit_log.jsonl"))


# ---------------------------------------------------------------- success: full E2E
@pytest.mark.parametrize("runner", [run_poc, run_baseline], ids=["poc", "baseline"])
def test_t06_end_to_end(tmp_path, runner):
    ctx = make_ctx(tmp_path)
    runner(ctx)
    pred = pd.read_csv(tmp_path / "out" / "release_decisions.csv")
    assert list(pred["release_id"]) == [f"r{i:02d}" for i in range(1, 21)]  # one row per release, sorted
    assert pred["release_id"].is_unique
    assert set(pred["decision"]) <= {"PASS", "HOLD", "REWORK"}
    assert set(pred["root_cause"]) <= {"class_swap", "bbox_shift", "id_collision", "dropped_frames",
                                       "stale_map", "clean", "parse_or_schema", "provenance", "schema"}
    # 5-step contract artifacts
    q = pd.read_csv(tmp_path / "out" / "review_queue.csv")
    assert len(q) == 12 and list(q["rank"]) == list(range(1, 13))
    assert set(q["suggested_action"]) <= {"PASS", "HOLD", "REWORK"}
    assert (tmp_path / "out" / "contact_sheet.html").exists()
    dec = json.loads((tmp_path / "out" / "decision.json").read_text(encoding="utf-8"))
    assert dec["owner"] == OWNER and dec["reason_code"] and dec["status"] in {"GO", "HOLD", "REWORK"}
    log = (tmp_path / "out" / "decision_log.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(log) == 2  # header + 1 batch decision row
    audit = (tmp_path / "out" / "audit_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert audit and all(json.loads(l)["actor"] for l in audit)


def test_t06_gate_blocks_planted_corruptions(tmp_path):
    """Sanity: planted silent corruptions are blocked with the right root cause; clean PASS."""
    ctx = make_ctx(tmp_path)
    run_poc(ctx)
    scored = pd.read_csv(tmp_path / "out" / "release_decisions.csv")
    got = dict(zip(scored["release_id"], scored["root_cause"]))
    dec = dict(zip(scored["release_id"], scored["decision"]))
    for rid, cause in {**DEV_DEFECTS, **EVAL_DEFECTS}.items():
        assert dec[rid] != "PASS", f"{rid} ({cause}) must be blocked"
        assert got[rid] == cause, f"{rid}: root cause {got[rid]} != {cause}"
    for rid in DEV_CLEAN + EVAL_CLEAN:
        assert dec[rid] == "PASS", f"clean {rid} must not be blocked (root_cause={got[rid]})"
        assert got[rid] == "clean"
    # batch decision covers the whole gate run
    d = json.loads((tmp_path / "out" / "decision.json").read_text(encoding="utf-8"))
    assert d["status"] == "REWORK" and d["metrics"]["n_blocked"] == 10
    # evidence: full diff report written for the reviewer
    diffs = json.loads((tmp_path / "out" / "release_diffs.json").read_text(encoding="utf-8"))
    assert set(diffs) == set(scored["release_id"])
    assert diffs["r01"]["violations"], "blocked releases must carry concrete evidence"


def test_t06_poc_beats_baseline_on_defect_families(tmp_path):
    """Baseline (parse + file-exists only) must miss every silent corruption; PoC blocks 10/20."""
    poc_ctx, base_ctx = make_ctx(tmp_path, "poc"), make_ctx(tmp_path, "baseline")
    run_poc(poc_ctx), run_baseline(base_ctx)
    poc = pd.read_csv(tmp_path / "poc" / "release_decisions.csv")
    base = pd.read_csv(tmp_path / "baseline" / "release_decisions.csv")
    assert (poc["decision"] != "PASS").sum() == 10
    # every JSON parses and every referenced file exists in the fixture -> baseline blocks nothing
    assert (base["decision"] == "PASS").all() and base["root_cause"].eq("clean").all()


def test_t06_outputs_are_deterministic(tmp_path):
    ctx1, ctx2 = make_ctx(tmp_path, "run1"), make_ctx(tmp_path, "run2")
    run_poc(ctx1), run_poc(ctx2)
    a = (tmp_path / "run1" / "release_decisions.csv").read_bytes()
    b = (tmp_path / "run2" / "release_decisions.csv").read_bytes()
    assert a == b  # byte-identical, same seed


# ---------------------------------------------------------------- failure / edge
def test_t06_rank_requires_score_column(tmp_path):
    ctx = make_ctx(tmp_path)
    with pytest.raises(ValueError, match="score"):
        rank(ctx, pd.DataFrame({"release_id": ["r01", "r02"], "path": ["x", "y"]}))


def test_t06_reviewed_file_rejects_bad_rows(tmp_path):
    p = tmp_path / "reviewed.csv"
    base = {"rank": [1], "item_id": ["r01"], "score": [1.0], "reason": [""], "suggested_action": [""],
            "slice": [""], "evidence_path": [""], "override_value": [""], "review_note": [""], "reviewed_at": [""]}
    # unknown decision value
    pd.DataFrame(base | {"reviewer": ["an"], "reviewer_decision": ["maybe"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="reviewer_decision"):
        load_review_decisions(p)
    # decision without an owner
    pd.DataFrame(base | {"reviewer": [""], "reviewer_decision": ["approve"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="reviewer"):
        load_review_decisions(p)
    # valid review file but an override_value outside the release-decision vocabulary
    ctx = make_ctx(tmp_path / "ctx")
    data = load(ctx)
    scored = process(ctx, data)
    queue = rank(ctx, scored)
    reviewed = queue.head(1).copy()
    reviewed["reviewer"], reviewed["reviewer_decision"], reviewed["override_value"] = "tester", "edit", "MAYBE"
    reviewed.to_csv(ctx.output_dir / "review_queue_reviewed.csv", index=False)
    with pytest.raises(ValueError, match="override_value"):
        review(ctx, scored, queue)


def test_t06_review_override_changes_decision_and_audits(tmp_path):
    ctx = make_ctx(tmp_path)
    data = load(ctx)
    scored = process(ctx, data)
    queue = rank(ctx, scored)
    top_id = queue.iloc[0]["item_id"]
    assert scored.set_index("release_id").loc[top_id, "decision"] == "HOLD"  # queue head is a blocked release
    reviewed = queue.head(1).copy()
    reviewed["reviewer"], reviewed["reviewer_decision"] = "tester", "edit"
    reviewed["override_value"] = "PASS"            # human disagrees: release anyway
    reviewed["review_note"] = "false alarm on dev"
    reviewed.to_csv(ctx.output_dir / "review_queue_reviewed.csv", index=False)
    final = review(ctx, scored, queue)
    row = final[final["release_id"] == top_id].iloc[0]
    assert row["decision"] == "PASS"
    assert ctx.stats.get("n_overridden") == 1
    log = [json.loads(l) for l in (ctx.output_dir / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["action"] == "override:edit" and e["actor"] == "tester" for e in log)


def test_t06_evaluator_flags_duplicate_and_missing_release_ids(tmp_path):
    """Edge: release_decisions.csv must carry ONE row per release; duplicates fail loudly,
    missing rows silently lower recall (merge fillna 'GO') — both are contract violations."""
    gt = pd.DataFrame({"release_id": [f"r{i:02d}" for i in range(1, 6)], "split": "eval",
                       "is_defective": [0, 1, 0, 1, 0],
                       "corruption_type": ["clean", "class_swap", "clean", "dropped_frames", "clean"]})
    gt_path = tmp_path / "gt_releases.csv"
    gt.to_csv(gt_path, index=False)
    eval_params = {"split": "eval"}
    # duplicate release_id -> evaluator raises
    dup = tmp_path / "dup.csv"
    pd.DataFrame({"release_id": ["r01", "r01", "r02"], "decision": ["PASS", "PASS", "HOLD"]}).to_csv(dup, index=False)
    with pytest.raises(ValueError, match="duplicate"):
        SPEC.evaluator(gt_path, dup, eval_params)
    # missing defective release in decisions -> it silently counts as GO -> recall < 1
    miss = tmp_path / "miss.csv"
    pd.DataFrame({"release_id": ["r01", "r03", "r04"], "decision": ["PASS", "PASS", "HOLD"]}).to_csv(miss, index=False)
    res = SPEC.evaluator(gt_path, miss, eval_params)
    primary = [m for m in res.metrics if m.primary][0]
    assert primary.value == pytest.approx(2 / 3)   # tp=1 (r04), fn=1 (r02 missing -> GO), fp=0
    # complete, correct decisions -> F1 = 1 on this mini-batch
    full = tmp_path / "full.csv"
    gt.assign(decision=["PASS", "HOLD", "PASS", "HOLD", "PASS"], root_cause=gt.corruption_type)[
        ["release_id", "decision", "root_cause"]].to_csv(full, index=False)
    res2 = SPEC.evaluator(gt_path, full, eval_params)
    assert [m for m in res2.metrics if m.primary][0].value == pytest.approx(1.0)


def test_t06_check_release_unit_signals(tmp_path):
    """Unit: each invariant family fires on a minimal synthetic release (label-free)."""
    ctx = make_ctx(tmp_path)
    data = load(ctx)
    p = {"shift_tol_px": 5.0, "min_shift_frac": 0.05, "bbox_tol_px": 0.5,
         "decision": {"rework_min_families": 2}}
    parent = data["parent"]
    def mk(mutate):
        ann = json.loads(json.dumps(parent))
        ann["info"] = {"version": "x"}
        mutate(ann)
        return ann
    rel = pd.Series({"release_id": "rX", "path": "releases/candidates/r01", "split": "dev"})
    # class_swap: permute car <-> pedestrian in categories
    def swap(ann):
        for c in ann["categories"]:
            if c["name"] == "car":
                c["name"] = "pedestrian"
            elif c["name"] == "pedestrian":
                c["name"] = "car"
    res = check_release(ctx, rel, {**data, "annotations.json": mk(swap), "release_meta.json":
                                   {"parent_sha256": data["parent_sha256"], "label_map_version": "lm-3"}}, p)
    assert "class_swap" in {v["family"] for v in res["violations"]}
    # bbox_shift: move every annotation 20 px on x
    def shift(ann):
        for a in ann["annotations"]:
            a["bbox"][0] += 20.0
    res2 = check_release(ctx, rel, {**data, "annotations.json": mk(shift), "release_meta.json":
                                    {"parent_sha256": data["parent_sha256"], "label_map_version": "lm-3"}}, p)
    assert "bbox_shift" in {v["family"] for v in res2["violations"]}
    # dropped_frames: remove 9 images of one sequence (and their annotations)
    def drop(ann):
        gone = {i["id"] for i in ann["images"] if i["sequence_id"] == "seq0" and 5 <= i["frame_index"] <= 13}
        ann["images"] = [i for i in ann["images"] if i["id"] not in gone]
        ann["annotations"] = [a for a in ann["annotations"] if a["image_id"] not in gone]
    res3 = check_release(ctx, rel, {**data, "annotations.json": mk(drop), "release_meta.json":
                                    {"parent_sha256": data["parent_sha256"], "label_map_version": "lm-3"}}, p)
    assert "dropped_frames" in {v["family"] for v in res3["violations"]}
    # id_collision: force two annotations onto the same id
    def collide(ann):
        ann["annotations"][1]["id"] = ann["annotations"][0]["id"]
    res4 = check_release(ctx, rel, {**data, "annotations.json": mk(collide), "release_meta.json":
                                    {"parent_sha256": data["parent_sha256"], "label_map_version": "lm-3"}}, p)
    fams = {v["family"] for v in res4["violations"]}
    assert "id_collision" in fams
    # provenance: wrong parent_sha256
    res5 = check_release(ctx, rel, {**data, "annotations.json": mk(lambda a: None),
                                    "release_meta.json": {"parent_sha256": "deadbeef", "label_map_version": "lm-3"}}, p)
    assert "provenance" in {v["family"] for v in res5["violations"]}
