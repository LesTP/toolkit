from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
from typing import Any


@dataclass(frozen=True)
class JudgeResult:
    verdict: str
    explanation: str
    criteria: str


class LLMJudge:
    def __init__(
        self,
        llm_client: Any,
        llm_config: dict[str, Any],
        tier: str = "commodity",
    ) -> None:
        self.llm_client = llm_client
        self.llm_config = llm_config
        self.tier = tier

    async def evaluate(
        self,
        response_text: str,
        criteria: str,
        pass_instruction: str,
        fail_instruction: str,
        context: str = "",
    ) -> JudgeResult:
        judge_response = await self._complete(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a strict prompt-regression judge. "
                        "Return exactly PASS|explanation or FAIL|explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": "\n\n".join(
                        [
                            "Criteria:",
                            criteria,
                            "Pass instruction:",
                            pass_instruction,
                            "Fail instruction:",
                            fail_instruction,
                            "Context:",
                            context,
                            "Response text:",
                            response_text,
                        ]
                    ),
                },
            ]
        )
        verdict, explanation = _parse_judge_response(judge_response)
        return JudgeResult(verdict=verdict, explanation=explanation, criteria=criteria)

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        response = self.llm_client.complete(
            messages=messages,
            config=self.llm_config,
            tier=self.tier,
        )
        if isawaitable(response):
            response = await response
        if not isinstance(response, str):
            raise ValueError("Judge LLM response must be plain text")
        return response


def _parse_judge_response(response_text: str) -> tuple[str, str]:
    verdict, separator, explanation = response_text.partition("|")
    if not separator:
        raise ValueError("Judge response must contain '|' separator")

    verdict = verdict.strip().upper()
    explanation = explanation.strip()
    if verdict not in {"PASS", "FAIL"}:
        raise ValueError("Judge verdict must be PASS or FAIL")
    if not explanation:
        raise ValueError("Judge explanation must not be blank")

    return verdict, explanation
