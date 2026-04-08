from __future__ import annotations

import json
from pathlib import Path


_EVAL_DIR = Path(__file__).with_name("evals")
_INTENT_CASE_PATH = _EVAL_DIR / "intent_cases.json"
_CLARIFICATION_CASE_PATH = _EVAL_DIR / "clarification_trigger_cases.json"
_CASE_LABELS = ("supported", "clarification", "unsupported")


def _load_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert isinstance(payload.get("families"), list)
    return payload


def _iter_cases(payload: dict) -> list[dict]:
    cases: list[dict] = []
    for family in payload["families"]:
        assert isinstance(family.get("family"), str)
        family_cases = family.get("cases")
        assert isinstance(family_cases, dict)
        for case_label in _CASE_LABELS:
            case_items = family_cases.get(case_label, [])
            assert isinstance(case_items, list)
            for case in case_items:
                assert isinstance(case, dict)
                cases.append(
                    {
                        "family": family["family"],
                        "case_label": case_label,
                        **case,
                    }
                )
    return cases


def test_eval_fixture_corpus_is_grouped_and_large_enough() -> None:
    intent_payload = _load_payload(_INTENT_CASE_PATH)
    clarification_payload = _load_payload(_CLARIFICATION_CASE_PATH)

    intent_cases = _iter_cases(intent_payload)
    clarification_cases = _iter_cases(clarification_payload)
    all_cases = [*intent_cases, *clarification_cases]

    assert len(all_cases) >= 150
    assert {case["case_label"] for case in all_cases} == set(_CASE_LABELS)
    assert len({case["family"] for case in all_cases}) >= 6


def test_eval_fixture_case_ids_are_unique() -> None:
    all_cases = [
        *_iter_cases(_load_payload(_INTENT_CASE_PATH)),
        *_iter_cases(_load_payload(_CLARIFICATION_CASE_PATH)),
    ]
    ids = [case["id"] for case in all_cases]
    assert len(ids) == len(set(ids))


def test_each_family_contains_all_case_labels() -> None:
    for path in (_INTENT_CASE_PATH, _CLARIFICATION_CASE_PATH):
        payload = _load_payload(path)
        for family in payload["families"]:
            family_cases = family["cases"]
            for case_label in _CASE_LABELS:
                assert family_cases.get(case_label), f"{path.name}:{family['family']} missing {case_label} cases"
