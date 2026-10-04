import asyncio
import pytest
from types import SimpleNamespace
from eval.evaluate import JudgePacer, ragas_scores

def test_pacer_spaces_all_attempts_without_real_sleep():
    current=[100.]; starts=[]; waits=[]
    async def sleep(delay):
        waits.append(delay);current[0]+=delay
    async def run():
        pace=JudgePacer(15,clock=lambda:current[0],sleep=sleep)
        for _ in range(6):
            await pace(None);starts.append(current[0])
    asyncio.run(run())
    assert starts == [100.,115.,130.,145.,160.,175.]
    assert waits == [15.]*5

@pytest.mark.parametrize('model,budget,interval',[
    ('gemini-2.5-flash',8192,15),('qwen/qwen3.8-27b',2048,60)])
def test_judge_reuses_scores_and_configures_output_budget(monkeypatch,model,budget,interval):
    import openai
    import ragas.llms
    import ragas.metrics.collections as metrics
    import eval.evaluate as evaluate
    calls=[]; progress=[]; configuration={}
    monkeypatch.setattr(evaluate,'settings',lambda:SimpleNamespace(
        judge_api_key='offline',judge_model=model,
        judge_base_url='https://example.invalid/',llm_timeout=60))
    monkeypatch.setattr(evaluate,'Store',lambda:None)
    monkeypatch.setattr(evaluate,'Retrieval',lambda s:SimpleNamespace(
        store=SimpleNamespace(failure=lambda *a:None),close=lambda:None))
    class Client:
        def __init__(self,**kwargs):
            self.kwargs=kwargs
            assert kwargs['http_client'].event_hooks['request'][0].interval==interval
        async def __aenter__(self):return self
        async def __aexit__(self,*args):await self.kwargs['http_client'].aclose()
    monkeypatch.setattr(openai,'AsyncOpenAI',Client)
    def factory(*a,**kw):configuration.update(kw);return object()
    monkeypatch.setattr(ragas.llms,'llm_factory',factory)
    class Metric:
        def __init__(self,**kw):pass
        async def ascore(self,**kw):calls.append(kw);return SimpleNamespace(value=0.75)
    for name in ('Faithfulness','AnswerRelevancy','ContextPrecision','ContextRecall'):
        monkeypatch.setattr(metrics,name,Metric)
    result=ragas_scores([{'id':'q1','question':'Q','gold_answer':'A'}],
        [{'answer':'A','evidence':[{'text':'A'}]}],existing=[{'faithfulness':1.}],
        on_progress=lambda i,row:progress.append((i,row)))
    assert len(calls)==3 and len(progress)==3
    assert result[0]['faithfulness']==1.
    assert result[0]['context_recall']==0.75
    assert configuration['max_tokens']==budget
    assert configuration['reasoning_effort']=='none'
    calls.clear(); progress.clear()
    result=ragas_scores([{'id':'q1','question':'Q','gold_answer':'A'}],
        [{'answer':'A','evidence':[{'text':'A'}]}],metrics=['faithfulness'],
        on_progress=lambda i,row:progress.append((i,row)))
    assert len(calls)==1 and len(progress)==1
    assert result==[{'faithfulness':0.75}]
