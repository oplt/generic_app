from types import SimpleNamespace

from backend.modules.ai.evaluation_scoring import evaluate_case, score_evaluation_case


def test_evaluation_scoring_reports_groundedness_and_citation_precision():
    case = SimpleNamespace(
        expected_output_text="PostgreSQL is the database",
        expected_output_json=None,
        expected_chunk_ids_json=["chunk-1"],
    )

    score, passed, notes = score_evaluation_case(
        "PostgreSQL is the database", None, ["chunk-1", "chunk-extra"], case
    )

    assert score == 1.0
    assert passed is True
    assert "rag-eval-v2" in notes
    assert "citation precision 0.50" in notes
    assert "groundedness 1.00" in notes


def test_unanswerable_case_requires_refusal():
    case = SimpleNamespace(
        evaluation_type="unanswerable",
        expected_output_text="I could not find relevant document context.",
        expected_output_json=None,
        expected_chunk_ids_json=[],
    )

    metrics = evaluate_case(
        "I could not find relevant document context.", None, [], case
    )

    assert metrics.passed is True
    assert metrics.answerability == 1.0


def test_explicit_source_citation_is_attributed_and_grounded():
    case = SimpleNamespace(
        evaluation_type="standard",
        expected_output_text="PostgreSQL is used.",
        expected_output_json=None,
        expected_chunk_ids_json=["chunk-1"],
    )

    metrics = evaluate_case(
        "[Source 1] PostgreSQL is used.",
        None,
        ["chunk-1"],
        case,
        retrieved_contents=["The project uses PostgreSQL as its database."],
    )

    assert metrics.passed is True
    assert metrics.citation_recall == 1.0
    assert metrics.groundedness == 1.0
