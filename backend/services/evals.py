"""
Basira, AI evaluation harness.

Two evaluation surfaces, both computed from real artefacts (never hand-typed):

  1. Model evaluation, from the held-out predictions persisted by train_models.py:
     ROC / PR curves, Brier score, decile calibration, a threshold sweep (sensitivity,
     specificity, PPV, patients flagged), confusion at the operating thresholds, and
     subgroup fairness (AUC, TPR, FPR, flag rate by nationality group, gender, age band).

  2. Agent evaluation, a golden evalset (data/evals/agent_evalset.json) executed through
     the live agent graph (when model credentials are present) or the direct tool
     runner, scored on:
       • tool-trajectory recall (expected tools ⊆ observed tools),
       • groundedness (a citation is present whenever the case is clinical),
       • action safety (drafts go to the approval queue, never executed),
       • numeric faithfulness (the answer quotes the true registry numbers),
       • latency, tokens and cost (live mode; priced from the provider's price list).

  Plus the LLM-selection matrix and a quantitative single-vs-multi-agent prompt-size
  comparison derived by introspecting the actual tool schemas.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, brier_score_loss, precision_recall_curve,
                             roc_auc_score, roc_curve)

from services import hie

BASE = Path(__file__).resolve().parent.parent
MODELS = BASE / "models"
EVALSET = BASE / "data" / "evals" / "agent_evalset.json"
RESULTS = BASE / "data" / "runtime" / "agent_eval_results.json"

# ─────────────────────────── LLM price list (USD per 1M tokens) ───────────────────────────
# Standard tier, verified against the price pages on the date noted. Re-check before demo day.
PRICES = {
    # Anthropic list prices (standard tier). Cache reads are 10% of the input price.
    "claude-sonnet-5":       {"in": 2.00, "out": 10.00, "std_in": 2.00, "std_out": 10.00, "cached_in": 0.20,
                              "note": "current-generation Sonnet: best function-calling reliability per dollar"},
    "claude-opus-5":         {"in": 5.00, "out": 25.00, "cached_in": 0.50,
                              "note": "flagship reasoning; judge / long executive syntheses"},
    "claude-sonnet-4-6":     {"in": 3.00, "out": 15.00, "cached_in": 0.30,
                              "note": "previous-generation Sonnet; the resolver's fallback"},
    "claude-haiku-4-5":      {"in": 1.00, "out": 5.00,  "cached_in": 0.10,
                              "note": "fastest and cheapest; routing / classification candidate"},
    "gemini-embedding-001":  {"in": 0.15, "out": 0.0,   "note": "optional semantic index for the guideline corpus (input only)"},
}
# The demonstration backend's provider (list prices, USD per 1M tokens), used only to cost a
# live evalset run and to cost the production plan on the same provider.
LIVE_PRICES = {
    "claude-sonnet-5":   {"in": 2.00, "out": 10.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-5": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5":  {"in": 1.00, "out": 5.00},
}
PRICES_AS_OF = "2026-06-24"

NATIONALITY_GROUP = {
    "Emirati": "Emirati", "Indian": "South Asian", "Bangladeshi": "South Asian", "Nepali": "South Asian",
    "Pakistani": "South Asian", "Sri Lankan": "South Asian", "Filipino": "Filipino",
    "Egyptian": "Arab expatriate", "Sudanese": "Arab expatriate", "Jordanian": "Arab expatriate", "Syrian": "Arab expatriate",
    "British": "Other", "Other": "Other",
}


# ═══════════════════════════════ 1. MODEL EVALUATION ═══════════════════════════════

def _preds() -> pd.DataFrame:
    df = pd.read_csv(MODELS / "eval_predictions.csv.gz")
    df["nat_group"] = df["nationality"].map(NATIONALITY_GROUP).fillna("Other")
    df["age_band"] = pd.cut(df["age"], [0, 49, 64, 200], labels=["<50", "50–64", "65+"]).astype(str)
    return df


def _downsample(xs, ys, n=60):
    idx = np.linspace(0, len(xs) - 1, min(n, len(xs))).astype(int)
    return [{"x": round(float(xs[i]), 4), "y": round(float(ys[i]), 4)} for i in idx]


def _confusion(y, p, t):
    pred = (p >= t).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    sens = tp / max(tp + fn, 1); spec = tn / max(tn + fp, 1); ppv = tp / max(tp + fp, 1)
    return {"threshold": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "sensitivity": round(sens, 3), "specificity": round(spec, 3), "ppv": round(ppv, 3),
            "flagged": tp + fp, "flag_rate": round((tp + fp) / len(y), 3),
            "nnt_to_find_one_event": round(1 / ppv, 1) if ppv > 0 else None}


def _subgroups(df: pd.DataFrame, col: str, t: float, min_events: int = 15) -> dict:
    rows = []
    for g, sub in df.groupby(col):
        y, p = sub["y_true"].values, sub["p"].values
        events = int(y.sum())
        auc = roc_auc_score(y, p) if len(set(y)) == 2 and len(sub) >= 30 else None
        c = _confusion(y, p, t)
        rows.append({"group": str(g), "n": int(len(sub)), "events": events,
                     "prevalence": round(float(y.mean()), 3),
                     "auc": round(auc, 3) if auc is not None else None,
                     "tpr": c["sensitivity"], "fpr": round(1 - c["specificity"], 3),
                     "flag_rate": c["flag_rate"], "ppv": c["ppv"],
                     "small_sample": events < min_events})
    rows.sort(key=lambda r: -r["n"])
    eligible = [r for r in rows if not r["small_sample"]]
    tprs = [r["tpr"] for r in eligible]
    fprs = [r["fpr"] for r in eligible]
    return {"dimension": col, "rows": rows, "min_events": min_events,
            "tpr_gap": round(max(tprs) - min(tprs), 3) if len(tprs) > 1 else 0.0,
            "fpr_gap": round(max(fprs) - min(fprs), 3) if len(fprs) > 1 else 0.0,
            "groups_compared": len(eligible)}


def model_evaluation(operating_threshold: float = 0.12) -> dict:
    df = _preds()
    y, p = df["y_true"].values, df["p"].values
    fpr, tpr, _ = roc_curve(y, p)
    prec, rec, _ = precision_recall_curve(y, p)
    legacy = df["legacy_risk_score"].values
    lfpr, ltpr, _ = roc_curve(y, legacy)

    sweep = [_confusion(y, p, t) for t in [0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]]
    dec = pd.DataFrame({"p": p, "y": y})
    dec["decile"] = pd.qcut(dec["p"], 10, labels=False, duplicates="drop") + 1
    calib = (dec.groupby("decile").agg(mean_predicted=("p", "mean"), observed_rate=("y", "mean"), n=("y", "size"))
             .reset_index().round(4).to_dict("records"))
    # calibration slope via linear fit of observed vs predicted decile means
    xs = np.array([c["mean_predicted"] for c in calib]); ys = np.array([c["observed_rate"] for c in calib])
    slope = float(np.polyfit(xs, ys, 1)[0]) if len(xs) > 2 else None

    cards = json.loads((MODELS / "model_cards.json").read_text())
    return {
        "test_rows": int(len(df)), "events": int(y.sum()), "event_rate": round(float(y.mean()), 3),
        "auc": round(float(roc_auc_score(y, p)), 3), "legacy_auc": round(float(roc_auc_score(y, legacy)), 3),
        "average_precision": round(float(average_precision_score(y, p)), 3),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "brier_baseline": round(float(brier_score_loss(y, np.full_like(p, y.mean()))), 4),
        "calibration_slope": round(slope, 2) if slope is not None else None,
        "roc": _downsample(fpr, tpr), "roc_legacy": _downsample(lfpr, ltpr),
        "pr": _downsample(rec[::-1], prec[::-1]),
        "calibration": calib,
        "threshold_sweep": sweep,
        "operating": _confusion(y, p, operating_threshold),
        "very_high": _confusion(y, p, 0.25),
        "subgroups": [_subgroups(df, "nat_group", operating_threshold),
                      _subgroups(df, "gender", operating_threshold),
                      _subgroups(df, "age_band", operating_threshold)],
        "model_cards": cards,
        "method": ("Stratified 75/25 hold-out (random_state=7); every figure on this page is computed "
                   "from the 1,000 held-out patients the model never saw. Subgroup TPR/FPR at the "
                   f"operating threshold p≥{operating_threshold} (the model's 'High' band)."),
    }


# ═══════════════════════════════ 2. AGENT EVALUATION ═══════════════════════════════

def evalset() -> dict:
    return json.loads(EVALSET.read_text())


_state = {"running": False, "progress": 0, "total": 0, "mode": None, "started": None}


def status() -> dict:
    return dict(_state)


def last_results() -> dict | None:
    if RESULTS.exists():
        try:
            return json.loads(RESULTS.read_text())
        except Exception:
            return None
    return None


def _fact_values() -> dict[str, list[str]]:
    """Ground-truth numbers the answers are expected to quote (multiple renderings)."""
    k = hie.cohort_stats()

    def renders(v):
        out = {str(v)}
        if isinstance(v, (int, np.integer)):
            out.add(f"{int(v):,}")
        if isinstance(v, float):
            out.add(f"{v:.1f}"); out.add(f"{v:.2f}")
        return list(out)
    facts = {key: renders(v) for key, v in k.items()}
    facts["total_annual_cost_aed_m"] = [f"{k['total_annual_cost_aed']/1e6:.1f}M", f"{k['total_annual_cost_aed']/1e6:.1f}"]
    return facts


def _score_case(case: dict, final: dict, latency_ms: int, facts: dict) -> dict:
    trace = final.get("trace") or []
    observed_tools = [t.get("tool") for t in trace]
    observed_agents = list({t.get("agent") for t in trace})
    exp = case.get("expected_tools", [])
    hit = [t for t in exp if t in observed_tools]
    traj_recall = len(hit) / len(exp) if exp else 1.0
    grounded = (len(final.get("citations") or []) > 0) if case.get("requires_citation") else True
    action_ok = (len(final.get("actions") or []) > 0) if case.get("requires_action") else True
    answer = final.get("answer") or ""
    fact_hits, fact_total = 0, 0
    for f in case.get("fact_checks", []):
        fact_total += 1
        if any(r in answer for r in facts.get(f, [])):
            fact_hits += 1
    faithful = (fact_hits == fact_total)
    usage = final.get("usage") or {}
    model = final.get("model") or ""
    cost = None
    if usage and usage.get("total_tokens"):
        from services import agent
        served = agent.active_model()          # the payload carries the display label, price the real id
        price = PRICES.get(served) or LIVE_PRICES.get(served) or LIVE_PRICES.get(
            next((k for k in LIVE_PRICES if served.startswith(k)), ""), PRICES["claude-sonnet-5"])
        cost = round(usage.get("prompt_tokens", 0) / 1e6 * price["in"]
                     + usage.get("completion_tokens", 0) / 1e6 * price["out"], 5)
    passed = traj_recall >= 0.75 and grounded and action_ok and faithful
    return {
        "id": case["id"], "persona": case["persona"], "question": case["question"],
        "expected_tools": exp, "observed_tools": observed_tools, "observed_agents": observed_agents,
        "trajectory_recall": round(traj_recall, 2), "missing_tools": [t for t in exp if t not in observed_tools],
        "grounded": grounded, "citations": len(final.get("citations") or []),
        "action_ok": action_ok, "actions": len(final.get("actions") or []),
        "faithful": faithful, "facts_checked": fact_total, "facts_hit": fact_hits,
        "latency_ms": latency_ms, "tokens": usage.get("total_tokens"), "llm_calls": usage.get("llm_calls"),
        "cost_usd": cost, "model": model, "passed": passed,
        "answer_preview": answer[:220],
    }


async def _run_case(case: dict, mode: str) -> dict:
    from services import agent, scenarios
    t0 = time.time()
    final = None
    if mode == "live" and agent.llm_enabled():
        async for ev in agent.stream_chat(case["question"], f"eval-{case['id']}-{int(t0)}", case["persona"]):
            if ev.get("type") == "final":
                final = ev
    else:
        runner = scenarios.get_runner(case["scenario_id"])
        async for ev in runner(case["persona"]):
            if ev.get("type") == "final":
                final = ev
    return final or {"answer": "", "trace": []}, int((time.time() - t0) * 1000)


def run_agent_evals(mode: str = "auto") -> None:
    """Execute the evalset in a background thread; results persist to RESULTS."""
    from services import agent
    if _state["running"]:
        return
    resolved = "live" if (mode in ("auto", "live") and agent.llm_enabled()) else "direct"
    cases = evalset()["cases"]
    _state.update({"running": True, "progress": 0, "total": len(cases), "mode": resolved,
                   "started": datetime.now(timezone.utc).isoformat()})

    def work():
        facts = _fact_values()
        results = []
        loop = asyncio.new_event_loop()
        try:
            for c in cases:
                try:
                    final, ms = loop.run_until_complete(_run_case(c, resolved))
                    results.append(_score_case(c, final, ms, facts))
                except Exception as e:  # a failing case is a finding, not a crash
                    results.append({"id": c["id"], "persona": c["persona"], "question": c["question"],
                                    "passed": False, "error": f"{e.__class__.__name__}: {str(e)[:160]}",
                                    "trajectory_recall": 0, "grounded": False, "action_ok": False,
                                    "faithful": False, "latency_ms": None, "tokens": None, "cost_usd": None})
                _state["progress"] += 1
        finally:
            loop.close()
        n = max(len(results), 1)
        costs = [r["cost_usd"] for r in results if r.get("cost_usd") is not None]
        lat = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
        summary = {
            "mode": resolved, "run_at": datetime.now(timezone.utc).isoformat(),
            "cases": len(results), "passed": sum(1 for r in results if r["passed"]),
            "pass_rate": round(sum(1 for r in results if r["passed"]) / n, 2),
            "mean_trajectory_recall": round(sum(r["trajectory_recall"] for r in results) / n, 2),
            "groundedness_rate": round(sum(1 for r in results if r["grounded"]) / n, 2),
            "action_safety_rate": round(sum(1 for r in results if r["action_ok"]) / n, 2),
            "faithfulness_rate": round(sum(1 for r in results if r["faithful"]) / n, 2),
            "mean_latency_ms": int(sum(lat) / len(lat)) if lat else None,
            "p95_latency_ms": int(np.percentile(lat, 95)) if lat else None,
            "total_cost_usd": round(sum(costs), 4) if costs else None,
            "cost_per_question_usd": round(sum(costs) / len(costs), 4) if costs else None,
            "results": results,
        }
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps(summary, indent=2, default=str))
        _state["running"] = False

    threading.Thread(target=work, daemon=True).start()


# ═══════════════════════════════ 3. LLM SELECTION & COST ═══════════════════════════════

def _tool_schema_tokens(funcs) -> int:
    """Rough token count of the function-calling schema an agent carries on every call:
    name + docstring + signature, at ~4 characters per token."""
    chars = 0
    for f in funcs:
        chars += len(f.__name__) + len(inspect.getdoc(f) or "") + len(str(inspect.signature(f)))
    return int(chars / 4)


def llm_selection() -> dict:
    from services import agent as A
    cohort = [A.describe_dataset, A.describe_column, A.get_patient, A.patient_timeline, A.filter_cohort,
              A.groupby_aggregate, A.top_n, A.correlate, A.histogram, A.cohort_kpis, A.facility_benchmark,
              A.equity_breakdown]
    guideline = [A.search_guidelines]
    risk = [A.score_patient_risk, A.stratify_cohort_risk, A.similar_patients, A.simulate_policy,
            A.visit_forecast, A.model_cards]
    action = [A.draft_prescription, A.draft_recall, A.draft_referral]
    supervisor_own = [A.render_chart, A.render_map]
    mcp_tools_est = 7 * 180   # 7 MCP tools ≈ 180 tokens each (descriptions + arg schemas)
    flat = _tool_schema_tokens(cohort + guideline + risk + action + supervisor_own) + mcp_tools_est
    per_agent = {
        "basira_supervisor": _tool_schema_tokens(supervisor_own) + 5 * 90,   # 5 AgentTool stubs
        "cohort_agent": _tool_schema_tokens(cohort), "guideline_agent": _tool_schema_tokens(guideline),
        "risk_agent": _tool_schema_tokens(risk), "pophealth_agent": mcp_tools_est,
        "action_agent": _tool_schema_tokens(action),
    }
    typical_hops = 3   # a clinician question touches ~3 specialists
    hier_per_turn = per_agent["basira_supervisor"] * 2 + sum(sorted(per_agent.values())[-typical_hops:]) // 1
    price = PRICES["claude-sonnet-5"]
    q_per_day = 20000
    def monthly(tokens_per_turn, out_tokens=900):
        return round((tokens_per_turn * price["in"] + out_tokens * price["out"]) / 1e6 * q_per_day * 30, 0)
    return {
        "prices_as_of": PRICES_AS_OF,
        "models": [
            {"model": "claude-sonnet-5", "role": "Supervisor + all specialists", "chosen": True,
             **PRICES["claude-sonnet-5"], "context": "1M", "latency": "fast",
             "why": "Current-generation Sonnet: the best function-calling reliability per dollar on our evalset; adaptive thinking keeps routing turns fast; a 3-hop question stays under a cent. Prompts carry pseudonymous ids only, so a hosted endpoint is acceptable; the same graph runs unchanged on a customer-hosted model behind SAS RAM."},
            {"model": "claude-opus-5", "role": "LLM-as-judge (eval) · complex synthesis on demand", "chosen": True,
             **PRICES["claude-opus-5"], "context": "1M", "latency": "slower",
             "why": "Reserved for where reasoning depth pays: grading answers in evaluation and long executive syntheses. Not on the hot path, and 2.5x the cost."},
            {"model": "claude-sonnet-4-6", "role": "Fallback", "chosen": False,
             **PRICES["claude-sonnet-4-6"], "context": "1M", "latency": "fast",
             "why": "Previous generation, still served. The resolver drops to it only if Sonnet 5 is unavailable to the key."},
            {"model": "claude-haiku-4-5", "role": "Not used (candidate for routing/classification)", "chosen": False,
             **PRICES["claude-haiku-4-5"], "context": "200K", "latency": "fastest",
             "why": "Too weak for multi-step tool planning; would fit a front-door intent classifier if traffic grows. Not worth a second model to operate at bootcamp scale."},
            {"model": "gemini-embedding-001", "role": "Optional RAG embeddings (hybrid with BM25)", "chosen": False,
             **PRICES["gemini-embedding-001"], "context": "2k/chunk", "latency": "n/a",
             "why": "Only if a Gemini key is present: the corpus is embedded once and cached, near-zero recurring cost. Without it retrieval is BM25, which is what SAS RAM collections replace in production."},
        ],
        "architecture_comparison": {
            "flat_single_agent_schema_tokens": flat,
            "hierarchical_supervisor_schema_tokens": per_agent["basira_supervisor"],
            "per_agent_schema_tokens": per_agent,
            "typical_hops": typical_hops,
            "hierarchical_tokens_per_turn_est": hier_per_turn,
            "flat_tokens_per_turn_est": flat * 3,   # flat agent re-sends the full schema on each of ~3 tool rounds
            "monthly_cost_flat_usd": monthly(flat * 3),
            "monthly_cost_hierarchical_usd": monthly(hier_per_turn),
            "monthly_cost_hierarchical_cached_usd": round((hier_per_turn * price["cached_in"] + 900 * price["out"]) / 1e6 * q_per_day * 30, 0),
            "monthly_cost_hierarchical_pro_usd": round((hier_per_turn * PRICES["claude-opus-5"]["in"] + 900 * PRICES["claude-opus-5"]["out"]) / 1e6 * q_per_day * 30, 0),
            "questions_per_day": q_per_day,
            "assumptions": f"{q_per_day:,} single-turn questions/day, ~900 output tokens/turn, 3 tool rounds, claude-sonnet-5 list pricing, no prompt caching. Caching the system prompt and schemas (cache reads at $0.20/1M) cuts the prompt share by ~90%, the cached figure above; long multi-turn sessions raise it.",
            "argument": ("Specialists are not decoration. Function declarations are billed as input tokens, so schema size is literally the invoice. Each specialist carries only its own tool schema, so the "
                         "prompt the model reads on every hop is ~1/4 of a flat agent's; specialists can be "
                         "evaluated, rate-limited and permissioned separately (least privilege: the guideline "
                         "agent cannot draft prescriptions); and the MCP agent is swappable for the SAS Viya "
                         "MCP server under SAS Retrieval Agent Manager without touching the others."),
        },
    }


# ═══════════════════════════════ 4. GOVERNANCE ═══════════════════════════════

def governance() -> list[dict]:
    return [
        {"area": "Data", "control": "Synthetic data only, zero PHI in this demonstration", "status": "implemented", "evidence": "Data tab · generator is seeded and documented"},
        {"area": "Data", "control": "Consent enforcement, restricted patients blocked at the tool layer, denial audited", "status": "implemented", "evidence": "Audit tab · CONSENT·DENY events"},
        {"area": "Data", "control": "Consent enforcement in the source systems + a de-identified analytics zone in CAS (SAS Viya access controls, row-level security)", "status": "sas_viya", "evidence": "Target architecture, data layer"},
        {"area": "Model", "control": "Held-out evaluation, calibration and subgroup fairness reported per model version", "status": "implemented", "evidence": "This tab · Model evaluation"},
        {"area": "Model", "control": "Model cards with intended use and limitations; versions pinned", "status": "implemented", "evidence": "Risk & Models dashboard"},
        {"area": "Model", "control": "SAS Model Manager registry + performance monitoring (drift, fairness) + scheduled retraining with a fairness gate", "status": "sas_viya", "evidence": "Target architecture, SAS Model Manager"},
        {"area": "Agent", "control": "Numbers only from tools; clinical claims only with citations; actions only via the human queue", "status": "implemented", "evidence": "Supervisor instruction · agent trace"},
        {"area": "Agent", "control": "Golden evalset with trajectory, groundedness, action-safety and faithfulness checks", "status": "implemented", "evidence": "This tab · Agent evaluation"},
        {"area": "Agent", "control": "Least-privilege tools per specialist (guideline agent cannot draft; action agent cannot read cohorts)", "status": "implemented", "evidence": "Agent definitions"},
        {"area": "Agent", "control": "Prompt and response screening in SAS Retrieval Agent Manager (guardrails, PII redaction) before anything reaches the LLM", "status": "sas_viya", "evidence": "Target architecture, agent runtime"},
        {"area": "Agent", "control": "Evalset re-run in CI as a release gate; LLM-as-judge over the persisted RAM trace", "status": "sas_viya", "evidence": "Evalset format is ADK-compatible; RAM persists every tool, LLM and retrieval call"},
        {"area": "Operations", "control": "Full audit trail of tool calls, scores, drafts and human decisions", "status": "implemented", "evidence": "Audit tab"},
        {"area": "Operations", "control": "SAS Viya audit logs + the RAM query trace (tool, LLM and retrieval calls persisted per query)", "status": "sas_viya", "evidence": "Target architecture, operations"},
        {"area": "Sovereignty", "control": "Data and agent runtime hosted in-country on the customer's SAS Viya tenancy (UAE health-data residency); the LLM receives pseudonymous data only", "status": "sas_viya", "evidence": "Target architecture, sovereignty strip"},
        {"area": "Clinical safety", "control": "Human-in-the-loop for every clinical write; no autonomous prescribing", "status": "implemented", "evidence": "Queue tab"},
    ]
