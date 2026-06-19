from __future__ import annotations

from backend.modules.ai.schemas import AiRunResponse


def run_to_response(run) -> AiRunResponse:
    return AiRunResponse(
        id=run.id,
        prompt_template_id=run.prompt_template_id,
        prompt_version_id=run.prompt_version_id,
        provider_key=run.provider_key,
        model_name=run.model_name,
        status=run.status,
        response_format=run.response_format,
        variables=run.variables_json,
        retrieval_query=run.retrieval_query,
        retrieved_chunk_ids=run.retrieved_chunk_ids_json,
        input_messages=run.input_messages_json,
        output_text=run.output_text,
        output_json=run.output_json,
        latency_ms=run.latency_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens,
        estimated_cost_micros=run.estimated_cost_micros,
        error_message=run.error_message,
        review_status=run.review_status,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )
