# TODO

- Fix the two currently failing clarification-option tests in `tests/test_natural_language_query_service.py`: `test_clarification_candidates_prefer_question_examples_over_irrelevant_raw_search_hits` and `test_clarification_candidates_cover_examples_and_dedupe_specialized_variants`. Both are currently failing because `response.candidate_series[*].clarification_option` is `None`.
