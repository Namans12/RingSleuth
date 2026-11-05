from __future__ import annotations

from src.run.run_case import _grounded_similar_cases, _reconcile_verdict, _what_changed
from src.agent.schemas import ActionEntry


def test_grounded_similar_cases_keeps_ids_from_graph_traversal_evidence():
    final_state = {
        "evidence": [
            {"type": "closed_cases", "data": [{"id": "CC-1383", "outcome": "cleared"}]},
        ],
    }
    assert _grounded_similar_cases(final_state, ["CC-1383", "CC-9999"]) == ["CC-1383"]


def test_grounded_similar_cases_keeps_ids_from_vector_search_evidence():
    # Regression test: assess_node's prompt points the LLM at retrieve_knowledge's
    # vector hits ("knowledge.similar_cases"), not the graph-traversal
    # "closed_cases" evidence -- a filter checking only the latter would zero
    # out every legitimate vector-retrieved match (the bug this locks in).
    final_state = {
        "evidence": [
            {"type": "closed_cases", "data": []},
            {"type": "knowledge", "data": {
                "knowledge": [], "similar_cases": [{"id": "CC-0141", "type": "ClosedCase"}],
            }},
        ],
    }
    assert _grounded_similar_cases(final_state, ["CC-0141", "CC-9999"]) == ["CC-0141"]


def test_grounded_similar_cases_rejects_self_cited_fraudcase_id():
    # Regression test: caught live on HHG-001's actual batch output --
    # retrieve_knowledge's "similar_cases" mixes ClosedCase AND FraudCase
    # vector hits together, and an earlier version of the grounding filter
    # accepted either. "CASE-HHG-001" is a FraudCase id (this pipeline's own
    # write), not a closed_cases_history.csv id, and must never be accepted
    # here even though it's a real graph vertex the vector search actually
    # returned.
    final_state = {
        "evidence": [
            {"type": "closed_cases", "data": []},
            {"type": "knowledge", "data": {
                "knowledge": [],
                "similar_cases": [
                    {"id": "CASE-HHG-001", "type": "FraudCase"},
                    {"id": "CC-1066", "type": "ClosedCase"},
                ],
            }},
        ],
    }
    assert _grounded_similar_cases(final_state, ["CASE-HHG-001", "CC-1066"]) == ["CC-1066"]


def test_grounded_similar_cases_drops_ids_not_seen_in_any_evidence():
    final_state = {"evidence": []}
    assert _grounded_similar_cases(final_state, ["CC-INVENTED"]) == []


def test_grounded_similar_cases_handles_missing_evidence_key():
    assert _grounded_similar_cases({}, ["CC-0141"]) == []


def _action(name: str) -> list[ActionEntry]:
    return [ActionEntry(action=name, route="auto", reason="x")]


def test_what_changed_nothing_when_actions_identical():
    assert _what_changed({"trigger_type": "risk_score"}, {}, _action("CLOSE_NO_FRAUD"), _action("CLOSE_NO_FRAUD")) == "nothing"


def test_what_changed_customer_report_denies_path():
    result = _what_changed(
        {"trigger_type": "customer_report"}, {"recurring_charge_detected": False},
        _action("VERIFY_WITH_CUSTOMER"), _action("BLOCK_CARD"),
    )
    assert "already on file" in result


def test_what_changed_customer_report_recurring_path():
    result = _what_changed(
        {"trigger_type": "customer_report"}, {"recurring_charge_detected": True},
        _action("VERIFY_WITH_CUSTOMER"), _action("CLOSE_NO_FRAUD"),
    )
    assert "recurring" in result.lower()


def test_what_changed_simulated_evidence_path():
    result = _what_changed(
        {"trigger_type": "risk_score"}, {"evidence_requests": [{"type": "customer_validation"}]},
        _action("VERIFY_WITH_CUSTOMER"), _action("BLOCK_CARD"),
    )
    assert "Simulated" in result


# --- _reconcile_verdict: consistency fix from TASK14_ALL_FRAUD_DIAGNOSTIC.md ---

def test_reconcile_verdict_plain_probability_thresholds_unchanged():
    assert _reconcile_verdict(0.9, None) == "fraud"
    assert _reconcile_verdict(0.1, None) == "legitimate"
    assert _reconcile_verdict(0.5, None) == "uncertain"


def test_reconcile_verdict_r3_confirmation_forces_legitimate_even_at_high_probability():
    # R3: the customer confirmed the transaction themselves -- CLOSE_NO_FRAUD
    # is policy_node's own final action; a "fraud" verdict would contradict it.
    assert _reconcile_verdict(0.95, "confirmed_legitimate") == "legitimate"


def test_reconcile_verdict_r7_recurring_downgrades_fraud_to_uncertain():
    # R7 explicitly says "Do not block" -- "fraud"/"closed_fraud" cannot
    # coexist with final actions that decline to block.
    assert _reconcile_verdict(0.92, "disputes_recurring") == "uncertain"


def test_reconcile_verdict_r7_recurring_does_not_touch_an_already_legitimate_verdict():
    assert _reconcile_verdict(0.1, "disputes_recurring") == "legitimate"


def test_reconcile_verdict_r7_recurring_does_not_touch_an_already_uncertain_verdict():
    assert _reconcile_verdict(0.5, "disputes_recurring") == "uncertain"


def test_reconcile_verdict_denies_and_no_reply_do_not_override_probability():
    # R2 (denies) and R4 (no_reply) are meant to change the RECOMMENDED
    # ACTIONS, not silently override the probability-derived verdict the
    # way R3/R7 do -- only R3 and R7 carry a documented "this settles it"
    # semantic that a plain denial or non-response doesn't.
    assert _reconcile_verdict(0.92, "denies") == "fraud"
    assert _reconcile_verdict(0.92, "no_reply") == "fraud"


async def _write_receipt(monkeypatch, *, corrupt=None):
    from unittest.mock import AsyncMock, MagicMock
    from src.run.run_case import _write_case_to_graph
    import src.ingestion.embeddings as embeddings
    monkeypatch.setattr(embeddings, "embed", lambda _: [[0.1, 0.2]])
    stored = {}
    async def call(name, args):
        if name == "tigergraph__add_nodes":
            stored.update(args["vertices"][0])
            return {}
        attrs = {key: value for key, value in stored.items() if key != "case_id"}
        if corrupt:
            attrs[corrupt] = "stale"
        return {"data": {"v_id": stored["case_id"], "attributes": attrs}}
    tg = MagicMock()
    tg.call = AsyncMock(side_effect=call)
    tg.upsert_vectors = AsyncMock()
    return await _write_case_to_graph(tg, "REVIEW-test-HHG-017",
        {"customer_id": "C1", "card_id": "C1-K1"},
        {"pattern": "card_testing", "fraud_probability": 0.86, "evidence_claims": ["Observed sequence"]},
        "fraud", "closed_fraud", 100.0)


def test_write_receipt_confirms_all_attributes(monkeypatch):
    import asyncio
    written, timestamp = asyncio.run(_write_receipt(monkeypatch))
    assert written is True
    assert timestamp


def test_matching_verdict_does_not_accept_stale_receipt(monkeypatch):
    import asyncio
    for field in ["status", "card_id", "fraud_probability", "exposure_usd", "summary", "written_at"]:
        written, _ = asyncio.run(_write_receipt(monkeypatch, corrupt=field))
        assert written is False, field
