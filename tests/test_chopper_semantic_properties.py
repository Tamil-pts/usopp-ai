"""Property checks for exact identity priority and untrusted model selection."""
import pytest
pytest.importorskip('hypothesis')
from hypothesis import given,settings,strategies as st
from unittest.mock import patch
from backend.core import semantic_retrieval as semantic,semantic_runtime as runtime
from backend.core.engineering_harness import checked_selection


@settings(max_examples=70,deadline=None)
@given(st.lists(st.floats(min_value=-1,max_value=1,allow_nan=False,allow_infinity=False),min_size=1,max_size=30))
def test_dense_scores_never_displace_exact_identity_or_duplicate_sources(scores):
    rows={position:{'id':position,'score':100 if position==0 else score,'file':f'Logical/F{position}.st','first':1,'text':'source','matchReason':'Exact symbol DO_MOTOR' if position==0 else 'Full-text search'} for position,score in enumerate(scores)}
    dense={position:score for position,score in reversed(list(enumerate(scores)))}
    with patch.object(runtime,'settings',return_value={'enabled':True,'rerank':False}):result=semantic.rank(rows,dense,'DO_MOTOR',{'used':True})
    assert result[0]['id']==0
    assert len(result)==len(scores) and {row['id'] for row in result}==set(rows)


@settings(max_examples=80,deadline=None)
@given(st.integers(min_value=2,max_value=10**15),st.sampled_from(['',' ', '\n',',',';']))
def test_unknown_fact_numbers_are_never_accepted(number,separator):
    facts=[{'id':'F1','sourceIds':['S1']}]
    ids,error=checked_selection('F1'+separator+'F'+str(number),facts)
    assert ids==[] and error
