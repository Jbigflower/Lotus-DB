import argparse
import asyncio
import importlib
import json
import math
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agent.lotus_agent import get_agent
from src.agent.verify import assess_risk_and_build_confirmation, detect_confirmation_intent


def _load_cases(dataset_path: Path) -> List[Dict[str, Any]]:
    lines = dataset_path.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out
 
 
def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    s = sorted(values)
    k = int(math.ceil((p / 100.0) * len(s))) - 1
    k = max(0, min(k, len(s) - 1))
    return float(s[k])
 
 
def _history_with_context(*, user_id: str) -> List[Dict[str, Any]]:
    return [{"role": "system", "content": json.dumps({"user_id": user_id}, ensure_ascii=False)}]
 
 
def _match_tool_call(
    *,
    expected: Dict[str, Any],
    planned: Dict[str, Any],
    mode: str,
) -> bool:
    if str(expected.get("tool_name") or "") != str(planned.get("tool_name") or ""):
        return False
    expected_args = expected.get("arguments") or {}
    planned_args = planned.get("arguments") or {}
    if not isinstance(expected_args, dict) or not isinstance(planned_args, dict):
        return False
    if mode == "exact":
        return expected_args == planned_args
    for k, v in expected_args.items():
        if k not in planned_args:
            return False
        if planned_args[k] != v:
            return False
    return True
 
 
def _tool_accuracy(
    *,
    expected_calls: List[Dict[str, Any]],
    planned_calls: List[Dict[str, Any]],
    mode: str,
) -> Tuple[int, int]:
    total = len(expected_calls)
    ok = 0
    
    # Superset match: check if expected calls appear in planned calls in relative order
    p_idx = 0
    for e_call in expected_calls:
        found = False
        while p_idx < len(planned_calls):
            if _match_tool_call(expected=e_call, planned=planned_calls[p_idx], mode=mode):
                found = True
                p_idx += 1  # Advance for next expected call
                break
            p_idx += 1
        if found:
            ok += 1
            
    return ok, total
 
 
def _first_high_risk_confirmation(user_input: str, planned_calls: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if detect_confirmation_intent(user_input):
        return None
    for c in planned_calls:
        tool_name = str(c.get("tool_name") or "")
        args = c.get("arguments") or {}
        if not isinstance(args, dict):
            continue
        confirmation = assess_risk_and_build_confirmation(tool_name=tool_name, tool_args=args)
        if confirmation and confirmation.get("risk_level") == "high":
            return confirmation
    return None
 
 
def _confirmation_matches(expected: Dict[str, Any], got: Dict[str, Any]) -> bool:
    if str(expected.get("action") or "") != str(got.get("action") or ""):
        return False
    if expected.get("risk_level") and expected.get("risk_level") != got.get("risk_level"):
        return False
    expected_payload = expected.get("payload") or {}
    got_payload = got.get("payload") or {}
    if not isinstance(expected_payload, dict) or not isinstance(got_payload, dict):
        return False
    for k, v in expected_payload.items():
        if k not in got_payload:
            return False
        if got_payload[k] != v:
            return False
    return True
 
 
def _failure_type(*, reason: str) -> str:
    r = reason.lower()
    if "tool_not_found" in r:
        return "TOOL_NOT_FOUND"
    if "argument" in r or "user_id" in r or "top_k" in r or "size" in r:
        return "ARGUMENT_INVALID"
    if "timeout" in r:
        return "TIMEOUT"
    if "forbidden" in r:
        return "PERMISSION_FORBIDDEN"
    if "intent" in r:
        return "INTENT_WRONG"
    return "STATE_NOT_CHANGED"
 
 
def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SAS Baseline with real planner on Golden Dataset")
    parser.add_argument("--dataset", type=str, default="tests/data/golden_dataset.jsonl")
    parser.add_argument("--match-mode", choices=["key_fields_only", "exact"], default="key_fields_only")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-id", type=str, default="")
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
 
    dataset_path = Path(args.dataset)
    cases = _load_cases(dataset_path)
    if args.case_id:
        cases = [c for c in cases if str(c.get("id") or "") == args.case_id]
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
 
    eval_mod = importlib.import_module("tests.agent.test_golden_dataset_eval")
    test_conftest = importlib.import_module("tests.agent.conftest")
 
    world0 = test_conftest.world.__wrapped__()  # type: ignore[attr-defined]
    tool_registry = test_conftest.tool_registry.__wrapped__(world0)  # type: ignore[attr-defined]
 
    total = len(cases)
    successes = 0
    failures: List[Dict[str, Any]] = []
    case_outputs: List[Dict[str, Any]] = []
 
    by_intent: Dict[str, Dict[str, Any]] = {}
    by_difficulty: Dict[str, Dict[str, Any]] = {}
 
    tool_total = 0
    tool_ok = 0
 
    tool_calls_per_case: List[int] = []
    max_step_limit = 3
    max_step_violations = 0
 
    latencies_ms: List[float] = []
 
    guardrail_total = 0
    guardrail_ok = 0
 
    forbidden_total = 0
    forbidden_ok = 0
 
    allowlist = set(tool_registry.keys())
 
    for case in cases:
        case_id = str(case.get("id") or "")
        intent = str(case.get("intent") or "unknown")
        difficulty = str(case.get("difficulty") or "unknown")
        query = str(case.get("query") or "")
 
        by_intent.setdefault(intent, {"total": 0, "success": 0})
        by_intent[intent]["total"] += 1
        by_difficulty.setdefault(difficulty, {"total": 0, "success": 0})
        by_difficulty[difficulty]["total"] += 1
 
        started = time.monotonic()
        planned_calls: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []
        all_planned_calls: List[Dict[str, Any]] = []
        all_tool_results: List[Dict[str, Any]] = []
        turns: List[Dict[str, Any]] = []
        confirmation: Optional[Dict[str, Any]] = None
        resolved: Dict[str, Any] = {}
        user_id = ""
        case_success = False
        failure_type = ""
        error_text = ""
        per_case_tool_calls = 0
 
        try:
            base_world = deepcopy(world0)
            resolved = eval_mod._resolve_placeholders(case, base_world)
            user_id = str(((resolved.get("context") or {}).get("user_id")) or "")
            if not user_id:
                raise ValueError("missing user_id in context")

            agent = get_agent('baseline_augment')
            
            # Use 'history' from resolved case if provided
            initial_history = resolved.get("history") or []
            system_context = _history_with_context(user_id=user_id)
            
            if not initial_history:
                initial_history = system_context
            else:
                # Prepend system context
                initial_history = system_context + initial_history
            
            # Deep copy to avoid mutating across cases
            current_history = deepcopy(initial_history)
            
            current_user_input = query
            max_turns = 5
            done_success = False
            
            call_index = 0
            for turn in range(max_turns):
                planned_calls = asyncio.run(agent.plan(user_input=current_user_input, history=current_history, user_id=user_id))
                planned_calls = planned_calls or []
                normalized_calls = []
                for tc in planned_calls:
                    call_id = tc.get("tool_call_id") or f"call_{call_index}"
                    call_index += 1
                    normalized_calls.append(
                        {
                            "tool_name": tc.get("tool_name"),
                            "arguments": tc.get("arguments"),
                            "tool_call_id": call_id,
                        }
                    )
                planned_calls = normalized_calls
                
                # Check Guardrails on FIRST turn only
                if turn == 0:
                    confirmation = _first_high_risk_confirmation(query, planned_calls)
                    if resolved.get("expected_requires_confirmation"):
                        guardrail_total += 1
                        expected_confirmation = resolved.get("expected_confirmation") or {}
                        if not isinstance(expected_confirmation, dict):
                            raise ValueError("expected_confirmation must be dict")
                        if not confirmation:
                            raise RuntimeError("guardrail_not_triggered")
                        if not _confirmation_matches(expected_confirmation, confirmation):
                            raise RuntimeError("guardrail_payload_mismatch")
                        guardrail_ok += 1
                        successes += 1
                        by_intent[intent]["success"] += 1
                        by_difficulty[difficulty]["success"] += 1
                        case_success = True
                        done_success = True
                        break

                    if resolved.get("expected_policy_violation") or resolved.get("expected_clarification"):
                        if planned_calls:
                            raise RuntimeError("expected_no_tool_calls")
                        successes += 1
                        by_intent[intent]["success"] += 1
                        by_difficulty[difficulty]["success"] += 1
                        case_success = True
                        done_success = True
                        break

                if not planned_calls:
                    break
                
                all_planned_calls.extend(planned_calls)
                per_case_tool_calls += len(planned_calls)
                
                if len(planned_calls) > max_step_limit:
                    max_step_violations += 1

                # Execute tools
                turn_tool_results = []
                
                # Prepare Assistant Message with Tool Calls
                assistant_tool_calls_data = []
                for tc in planned_calls:
                    assistant_tool_calls_data.append({
                        "name": tc["tool_name"],
                        "args": tc["arguments"],
                        "id": tc["tool_call_id"]
                    })
                
                # Append User Input (if any) and Assistant Message to History
                if current_user_input:
                    current_history.append({"role": "user", "content": current_user_input})
                    current_user_input = "" # Clear for next turns
                
                current_history.append({"role": "assistant", "content": "", "tool_calls": assistant_tool_calls_data})
                
                # Execute and Append Tool Results
                for tc in planned_calls:
                    tool_name = str(tc.get("tool_name") or "")
                    call_args = tc.get("arguments") or {}
                    call_id = tc.get("tool_call_id") or ""
                    
                    if tool_name not in allowlist:
                        raise RuntimeError(f"tool_not_found:{tool_name}")
                    if not isinstance(call_args, dict):
                        raise RuntimeError("argument_invalid")
                    
                    try:
                        res = tool_registry[tool_name](base_world, call_args)
                    except Exception as e:
                        res = {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": str(e)}}
                        
                    turn_tool_results.append(res)
                    all_tool_results.append(res)
                    
                    # Append Tool Message
                    content_str = json.dumps(res, ensure_ascii=False)
                    current_history.append({"role": "tool", "content": content_str, "tool_call_id": call_id})

                turns.append({"planned_tool_calls": planned_calls, "tool_results": turn_tool_results})
                
                # Check for Forbidden errors in this turn
                expected_error = resolved.get("expected_error")
                if expected_error and str(expected_error.get("code")) == "FORBIDDEN":
                    for r in turn_tool_results:
                         if r.get("ok") is False:
                            code = str(((r.get("error") or {}).get("code")) or "")
                            if code == "FORBIDDEN":
                                 forbidden_total += 1
                                 forbidden_ok += 1
                                 successes += 1
                                 by_intent[intent]["success"] += 1
                                 by_difficulty[difficulty]["success"] += 1
                                 done_success = True
                                 break
                    if done_success:
                        break

            if done_success:
                continue

            # Verification Phase
            expected_calls = resolved.get("expected_tool_calls") or []
            if not isinstance(expected_calls, list):
                raise ValueError("expected_tool_calls must be list")

            ok_i, total_i = _tool_accuracy(expected_calls=expected_calls, planned_calls=all_planned_calls, mode=args.match_mode)
            tool_ok += ok_i
            tool_total += total_i
            
            # Check Expected Error (if not caught in loop)
            expected_error = resolved.get("expected_error")
            if expected_error:
                if not all_tool_results:
                     raise RuntimeError("expected_error_but_no_tool_results")
                expected_code = str((expected_error.get("code") or ""))
                matched = False
                any_error = False
                for res in all_tool_results:
                    if res.get("ok") is False:
                        any_error = True
                        got_code = str(((res.get("error") or {}).get("code")) or "")
                        if expected_code == got_code:
                            matched = True
                            break
                if not any_error:
                    raise RuntimeError("expected_error_but_ok")
                if not matched:
                    raise RuntimeError("expected_error_code_mismatch")
                if expected_code == "FORBIDDEN":
                    forbidden_total += 1
                    forbidden_ok += 1
                successes += 1
                by_intent[intent]["success"] += 1
                by_difficulty[difficulty]["success"] += 1
                case_success = True
                continue

            if expected_calls:
                if ok_i < total_i:
                    raise RuntimeError(f"tool_mismatch: found {ok_i}/{total_i}")

            sc = resolved.get("expected_state_change") or {}
            if sc:
                eval_mod._assert_state_change(sc, base_world, all_tool_results)

            successes += 1
            by_intent[intent]["success"] += 1
            by_difficulty[difficulty]["success"] += 1
            case_success = True
        except Exception as e:
            failure_type = _failure_type(reason=repr(e))
            error_text = repr(e)
            failures.append(
                {
                    "id": case_id,
                    "intent": intent,
                    "difficulty": difficulty,
                    "query": query,
                    "planned_tool_calls": planned_calls,
                    "expected_tool_calls": case.get("expected_tool_calls") or [],
                    "failure_type": failure_type,
                    "error": error_text,
                }
            )
        finally:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            latencies_ms.append(elapsed_ms)
            tool_calls_per_case.append(per_case_tool_calls)
            case_outputs.append(
                {
                    "id": case_id,
                    "intent": intent,
                    "difficulty": difficulty,
                    "query": query,
                    "user_id": user_id,
                    "success": case_success,
                    "failure_type": failure_type,
                    "error": error_text,
                    "expected_tool_calls": case.get("expected_tool_calls") or [],
                    "expected_error": resolved.get("expected_error"),
                    "expected_requires_confirmation": resolved.get("expected_requires_confirmation"),
                    "confirmation": confirmation,
                    "planned_tool_calls": all_planned_calls,
                    "tool_results": all_tool_results,
                    "turns": turns,
                }
            )
 
    sr = successes / total if total else 0.0
    ta = (tool_ok / tool_total) if tool_total else 1.0
    guardrail_rate = (guardrail_ok / guardrail_total) if guardrail_total else 1.0
    forbidden_rate = (forbidden_ok / forbidden_total) if forbidden_total else 1.0
    max_step_violation_rate = (max_step_violations / total) if total else 0.0
 
    report = {
        "git_like_version": datetime.now(timezone.utc).strftime("%Y%m%d"),
        "arch": {"arch_type": "sas_baseline", "route": "single_agent", "state": "real_planner_offline_world"},
        "metrics": {
            "success_rate": sr,
            "tool_accuracy": ta,
            "total_cases": total,
            "passed_cases": successes,
            "failed_cases": len(failures),
            "tool_calls_per_case_avg": (sum(tool_calls_per_case) / len(tool_calls_per_case)) if tool_calls_per_case else 0.0,
            "max_step_violation_rate": max_step_violation_rate,
            "latency_ms_p50": _percentile(latencies_ms, 50),
            "latency_ms_p95": _percentile(latencies_ms, 95),
            "guardrail_trigger_rate": guardrail_rate,
            "forbidden_operation_block_rate": forbidden_rate,
        },
        "by_intent": by_intent,
        "by_difficulty": by_difficulty,
        "failures": failures,
    }
 
    if args.output:
        out_path = Path(args.output)
        output_dir = out_path.parent
    else:
        output_dir = Path("data") / "agent_eval" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = output_dir / "report.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    cases_path = output_dir / "cases.jsonl"
    cases_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in case_outputs),
        encoding="utf-8",
    )

    print(str(out_path))
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
 
    return 0 if not failures else 1
 
 
if __name__ == "__main__":
    raise SystemExit(main())
