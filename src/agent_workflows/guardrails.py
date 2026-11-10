"""Agent execution guardrails: bounded context, explicit tool policies and prompt-injection signals.

Heuristic injection screening is defense-in-depth, NOT a security boundary.
Authorization and tool allowlists remain mandatory at invocation time.
"""
import re
from dataclasses import dataclass

class GuardrailViolation(ValueError):
    pass

MAX_QUESTION_CHARS = 2000
MAX_ESTIMATED_TOKENS = 3000
MAX_EVIDENCE_CHARS = 16000

# Narrowly scoped suspicious instructions; never treat a regex as complete protection.
_INJECTION = re.compile(
    r"(?i)(ignore (all |the )?(previous|system|developer) instructions|"
    r"reveal (the )?(system prompt|api key|secret)|"
    r"override (the )?(tool|security|authorization) policy)"
)

@dataclass(frozen=True)
class Budget:
    max_input_tokens: int = MAX_ESTIMATED_TOKENS
    max_tool_calls: int = 12
    max_llm_calls: int = 1

def estimated_tokens(text: str) -> int:
    # Conservative approximate budget; provider token counts may differ.
    return (len(text.encode("utf-8")) + 2) // 3

def validate_input(question: str, *, budget: Budget = Budget()) -> str:
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= MAX_QUESTION_CHARS:
        raise GuardrailViolation("Invalid question length")
    clean = question.strip()
    if estimated_tokens(clean) > budget.max_input_tokens:
        raise GuardrailViolation("Input token budget exceeded")
    if _INJECTION.search(clean):
        raise GuardrailViolation("Potential instruction override detected")
    return clean

def validate_evidence(evidence: list[dict], *, budget: Budget = Budget()) -> list[dict]:
    if not isinstance(evidence, list) or len(evidence) > 10:
        raise GuardrailViolation("Evidence count exceeded")
    size = 0
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise GuardrailViolation("Invalid evidence")
        size += len(item["text"])
        if size > MAX_EVIDENCE_CHARS or estimated_tokens(str(evidence)) > budget.max_input_tokens:
            raise GuardrailViolation("Evidence context budget exceeded")
    return evidence

def validate_execution(result: dict, *, budget: Budget = Budget()) -> dict:
    if not isinstance(result, dict):
        raise GuardrailViolation("Invalid agent result")
    if result.get("tool_calls", 0) > budget.max_tool_calls:
        raise GuardrailViolation("Tool budget exceeded")
    if result.get("llm_calls", 0) > budget.max_llm_calls:
        raise GuardrailViolation("LLM budget exceeded")
    return result
