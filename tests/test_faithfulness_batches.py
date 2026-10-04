import asyncio
import pytest
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness
from ragas.metrics.collections.faithfulness.util import NLIStatementOutput
from eval.evaluate import make_faithfulness

def test_each_statement_is_judged_with_full_context_and_same_score(monkeypatch):
    seen=[]
    async def verdict(self,statements,context):
        seen.append((statements,context))
        return NLIStatementOutput(statements=[{'statement':statements[0],
            'reason':'offline verdict','verdict':int(statements[0]!='unsupported')}])
    monkeypatch.setattr(Faithfulness,'_create_verdicts',verdict)
    client=AsyncOpenAI(api_key='offline',base_url='https://example.invalid/')
    judge=llm_factory('qwen/qwen3.8-27b',client=client)
    metric=make_faithfulness(judge,1)
    result=asyncio.run(metric._create_verdicts(['supported','unsupported','supported again'],
                                            'Complete original evidence'))
    assert seen==[(['supported'],'Complete original evidence'),
                  (['unsupported'],'Complete original evidence'),
                  (['supported again'],'Complete original evidence')]
    assert metric._compute_score(result)==pytest.approx(2/3)
    asyncio.run(client.close())

def test_missing_verdict_is_not_silently_scored(monkeypatch):
    async def omitted(*a):return NLIStatementOutput(statements=[])
    monkeypatch.setattr(Faithfulness,'_create_verdicts',omitted)
    client=AsyncOpenAI(api_key='offline',base_url='https://example.invalid/')
    metric=make_faithfulness(llm_factory('qwen/qwen3.8-27b',client=client),1)
    with pytest.raises(ValueError,match='omitted'):
        asyncio.run(metric._create_verdicts(['claim'],'Full context'))
    asyncio.run(client.close())
