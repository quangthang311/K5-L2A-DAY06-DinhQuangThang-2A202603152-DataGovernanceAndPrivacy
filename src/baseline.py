"""T06 *baseline* (group-owned): parse JSON/schema + file-existence check ONLY.

Exactly the bar the handout sets for T06 (§4): "Chỉ parse JSON/schema + kiểm
file tồn tại; không so semantic invariants." Every silent corruption in the
fixture (class map đảo, bbox lệch, trùng ID, rơi frame, map cũ) is *valid*
JSON pointing at existing files, so this baseline is expected to block
nothing — the PoC (src/pipeline.py) must beat it on the same pool / seed.

    python -m src.main --track t06 --pipeline src.baseline --output out/baseline --run-name baseline --offline

A release is HOLD only when annotations.json / release_meta.json is
unparseable, the COCO top-level schema is broken, or a referenced image file
is missing on disk. No comparison against the parent release happens here.
"""
from __future__ import annotations

import json

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track

REQUIRED_RELEASE_COLUMNS = ["release_id", "path", "split"]
COCO_KEYS = ["info", "images", "annotations", "categories"]
RELEASE_DECISIONS = {"PASS", "HOLD", "REWORK"}
DEFAULTS = {"budget": 12}


def load(ctx: RunContext) -> pd.DataFrame:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="baseline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    releases = pd.read_csv(ctx.input_dir / "releases.csv", dtype={"release_id": str})
    missing = [c for c in REQUIRED_RELEASE_COLUMNS if c not in releases.columns]
    if missing:
        raise ValueError(f"releases.csv missing required columns {missing}")
    ctx.audit.log(actor="baseline", action="load", item_id=str(ctx.input_dir), after={"n_releases": len(releases)})
    return releases


def process(ctx: RunContext, releases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rel in releases.itertuples(index=False):
        errors: list[str] = []
        ann_path = ctx.input_dir / rel.path / "annotations.json"
        meta_path = ctx.input_dir / rel.path / "release_meta.json"
        ann = meta = None
        try:
            ann = json.loads(ann_path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"annotations.json unparseable: {e}")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"release_meta.json unparseable: {e}")
        if isinstance(ann, dict):
            for k in COCO_KEYS:
                if k not in ann:
                    errors.append(f"annotations.json missing key '{k}'")
            for i in ann.get("images", []):
                if not (ctx.input_dir / str(i.get("file_name", ""))).exists():
                    errors.append(f"referenced image file missing: {i.get('file_name')}")
        blocked = bool(errors)
        rows.append({"release_id": rel.release_id, "split": rel.split, "path": rel.path,
                     "score": 1.0 if blocked else 0.0,
                     "decision": "HOLD" if blocked else "PASS",
                     "root_cause": "parse_or_schema" if blocked else "clean",
                     "reason": "; ".join(errors) or "JSON parses, schema keys present, all referenced files exist "
                               "(no semantic invariant checked — baseline handout T06 §4)"})
    df = pd.DataFrame(rows)
    ctx.stats["n_releases"] = len(df)
    ctx.stats["n_blocked"] = int((df["decision"] != "PASS").sum())
    ctx.stats["block_rate"] = float((df["decision"] != "PASS").mean()) if len(df) else 0.0
    return df


def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    p = {**DEFAULTS, **(ctx.config.get("params") or {})}
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first)")
    q = make_review_queue(scored, id_col="release_id", score_col="score", budget=int(p["budget"]),
                          reason_col="reason", action_col="decision", slice_col="split", evidence_col="path")
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_col=None,
                         fields=("rank", "item_id", "score", "reason", "suggested_action", "slice"),
                         title=f"t06 baseline (parse + file-exists only) — review queue ({ctx.run_name})")
    return q


def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        values = {v.strip() for v in reviewed["override_value"] if str(v).strip()}
        bad = sorted(values - RELEASE_DECISIONS)
        if bad:
            raise ValueError(f"reviewed file has invalid override_value {bad}; allowed {sorted(RELEASE_DECISIONS)}")
        return apply_overrides(scored, reviewed, id_col="release_id", value_col="decision", audit=ctx.audit)
    return scored


def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    n_blocked = int((final["decision"] != "PASS").sum())
    return Decision(status="HOLD", reason_code="BASELINE_ONLY",
                    reason=f"Parse/schema + file-existence baseline: {n_blocked}/{len(final)} blocked, "
                           f"0 semantic invariants checked — never release on this.",
                    owner=ctx.config.get("owner") or "TODO-owner", scope=ctx.track,
                    evidence=[str(ctx.out("release_decisions.csv"))],
                    metrics={"block_rate": float((final["decision"] != "PASS").mean()) if len(final) else 0.0,
                             "n_blocked": n_blocked})


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    releases = load(ctx)                              # 01 load
    scored = process(ctx, releases)                   # 02 process (parse + file-exists only)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)                         # 03 rank
    final = review(ctx, scored, queue)                # 04 review
    cols = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[cols].sort_values("release_id").to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
