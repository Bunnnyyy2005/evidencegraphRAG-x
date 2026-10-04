"""Atomic answer records; only entailed claims survive verification."""
from typing import Literal
from pydantic import BaseModel, Field
from .utils import RateLimitError

class Claim(BaseModel):
    text: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)

class Answer(BaseModel):
    claims: list[Claim] = Field(max_length=20)

class Verdict(BaseModel):
    label: Literal['ENTAILMENT', 'PARTIAL_SUPPORT', 'CONTRADICTION', 'INSUFFICIENT_EVIDENCE']
    reason: str


def valid_citations(claim: Claim, evidence: list[dict]) -> bool:
    return bool(claim.citations) and set(claim.citations).issubset({c['chunk_id'] for c in evidence})


def verify(answer: Answer, evidence: list[dict], llm, enabled: bool = True) -> tuple[list[dict], list[dict]]:
    """A verifier outage never promotes an unverified claim to supported."""
    evidence_map = {c['chunk_id']: c for c in evidence}
    accepted, audit = [], []
    for claim in answer.claims:
        label, reason = 'INSUFFICIENT_EVIDENCE', 'Citation is not part of retrieved evidence'
        if not valid_citations(claim, evidence):
            llm.store.failure('citation', ValueError('Citation outside retrieved evidence'))
        if valid_citations(claim, evidence):
            if not enabled:
                label, reason = 'NOT_VERIFIED', 'Verifier disabled for this ablation'
            else:
                try:
                    verdict = llm.json('Check this atomic claim against ONLY its cited ORIGINAL evidence. '
                        'ENTAILMENT requires every part, including numbers and qualifiers, to be supported. '
                        'Classify contradictions, partial and missing support conservatively.',
                        {'claim': claim.text, 'evidence': [evidence_map[c]['text'] for c in claim.citations]}, Verdict)
                    label, reason = verdict.label, verdict.reason
                except RateLimitError as exc:
                    llm.store.failure('verification', exc)
                    reason = str(exc)
                except Exception as exc:
                    llm.store.failure('verification', exc)
                    reason = 'Verification unavailable; claim removed'
        record = {**claim.model_dump(), 'status': label, 'reason': reason}
        audit.append(record)
        if label in ('ENTAILMENT', 'NOT_VERIFIED'):
            accepted.append(record)
    return accepted, audit


def render_claims(claims: list[dict], evidence: list[dict]) -> str:
    by_id = {c['chunk_id']: c for c in evidence}
    return '\n\n'.join(c['text'] + ' ' + ' '.join(
        f'[{by_id[cid]["document_name"]}, p.{by_id[cid]["page_number"]}]'
        for cid in dict.fromkeys(c['citations'])) for c in claims)
