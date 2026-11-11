"""Tiny synthetic Inspect task run offline against mockllm/model (no API calls)."""

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.solver import generate


@task
def synthetic_smoke():
    # Synthetic samples. mockllm/model replies with a fixed default string,
    # so the scores only show the export shape, not model quality.
    return Task(
        dataset=[
            Sample(
                input="Reply with the words: Default output from mockllm/model",
                target="Default output from mockllm/model",
                id="SYN-1",
                metadata={"requirement_id": "REQ-001"},
            ),
            Sample(
                input="What is 2 + 2?",
                target="4",
                id="SYN-2",
                metadata={"requirement_id": "REQ-004"},
            ),
            Sample(
                input="Name the capital of France.",
                target="Paris",
                id="SYN-3",
                metadata={"requirement_id": "REQ-004"},
            ),
        ],
        solver=generate(),
        scorer=includes(),
    )
