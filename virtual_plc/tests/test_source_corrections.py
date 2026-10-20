"""Atomic, source-guarded correction composition for virtual program copies."""
from copy import deepcopy
import hashlib

import pytest

from virtual_plc.core.source_corrections import apply_corrections
from virtual_plc.tests.test_runtime import project, variable


def correction(model, original, replacement, program_index=0, **extra):
    program = model['programs'][program_index]
    return {'source': program['source'], 'codeSha256': hashlib.sha256(program['code'].encode('utf-8')).hexdigest(),
            'original': original, 'replacement': replacement, 'reason': 'Explicit fixture correction', **extra}


def test_disjoint_corrections_to_one_source_compose_against_original_hash():
    model = project('A:=1;\nB:=2;', [variable('A'), variable('B')])
    document = {'schemaVersion': 1, 'corrections': [correction(model, 'A:=1;', 'A:=10;', line=1),
                                                   correction(model, 'B:=2;', 'B:=20;', line=2)]}
    result = apply_corrections(model, document)
    assert result is model
    program = model['programs'][0]
    assert program['code'] == 'A:=10;\nB:=20;'
    assert program['originalCode'] == 'A:=1;\nB:=2;'
    assert program['simulationCorrections'] == document['corrections']
    assert program['simulationCorrection'] == document['corrections'][-1]
    assert model['sourceCorrections'] == document
    assert [d['line'] for d in model['diagnostics']] == [1, 2]
    assert all(d['code'] == 'SIMULATION_SOURCE_CORRECTION' for d in model['diagnostics'])


def test_failed_later_correction_leaves_entire_model_untouched():
    model = project('A:=1;\nB:=2;', [variable('A'), variable('B')],
                    diagnostics=[{'code': 'EXISTING', 'message': 'Preserve this finding'}])
    before = deepcopy(model)
    document = {'schemaVersion': 1, 'corrections': [correction(model, 'A:=1;', 'A:=10;'),
                                                   correction(model, 'Missing:=2;', 'Missing:=20;')]}
    with pytest.raises(ValueError, match='exact expression'):
        apply_corrections(model, document)
    assert model == before


def test_failed_later_source_does_not_commit_an_earlier_program():
    model = project('A:=1;', [variable('A')])
    model['programs'].append({'id': 'other', 'source': 'Logical/Other/Main.st', 'code': 'B:=2;'})
    before = deepcopy(model)
    document = {'schemaVersion': 1, 'corrections': [correction(model, 'A:=1;', 'A:=10;'),
                                                   correction(model, 'B:=2;', 'B:=20;', 1, codeSha256='0'*64)]}
    with pytest.raises(ValueError, match='Source changed'):
        apply_corrections(model, document)
    assert model == before


def test_every_hash_references_original_code_not_intermediate_replacement():
    model = project('A:=1; B:=2;', [variable('A'), variable('B')])
    before = deepcopy(model)
    intermediate_hash = hashlib.sha256(b'A:=10; B:=2;').hexdigest()
    document = {'schemaVersion': 1, 'corrections': [correction(model, 'A:=1;', 'A:=10;'),
                                                   correction(model, 'B:=2;', 'B:=20;', codeSha256=intermediate_hash)]}
    with pytest.raises(ValueError, match='Source changed'):
        apply_corrections(model, document)
    assert model == before


def test_duplicate_and_overlapping_original_spans_are_rejected_atomically():
    model = project('A:=1; B:=2; C:=3;', [variable('A'), variable('B'), variable('C')])
    fixtures = [
        [correction(model, 'A:=1;', 'A:=1; (* simulation *)'), correction(model, 'A:=1;', 'A:=2;')],
        [correction(model, 'A:=1; B:=2;', 'A:=9; B:=2;'), correction(model, 'B:=2; C:=3;', 'B:=2; C:=9;')],
        [correction(model, 'A:=1; B:=2;', 'A:=9; B:=7;'), correction(model, 'B:=2;', 'B:=9;')],
    ]
    for items in fixtures:
        before = deepcopy(model)
        with pytest.raises(ValueError):
            apply_corrections(model, {'schemaVersion': 1, 'corrections': items})
        assert model == before


def test_missing_reason_or_changed_line_count_fails_before_any_commit():
    model = project('A:=1; B:=2;', [variable('A'), variable('B')])
    for second in [correction(model, 'B:=2;', 'B:=20;', reason=''),
                   correction(model, 'B:=2;', 'B:=2;\nB:=20;')]:
        before = deepcopy(model)
        with pytest.raises(ValueError):
            apply_corrections(model, {'schemaVersion': 1, 'corrections': [correction(model, 'A:=1;', 'A:=10;'), second]})
        assert model == before


def test_first_original_code_and_single_item_metadata_survive_later_review():
    model = project('A:=1;', [variable('A')])
    first = correction(model, 'A:=1;', 'A:=2;')
    apply_corrections(model, {'schemaVersion': 1, 'corrections': [first]})
    assert model['programs'][0]['simulationCorrection'] == first
    second = correction(model, 'A:=2;', 'A:=3;')
    apply_corrections(model, {'schemaVersion': 1, 'corrections': [second]})
    program = model['programs'][0]
    assert program['originalCode'] == 'A:=1;'
    assert program['code'] == 'A:=3;'
    assert program['simulationCorrection'] == second
    assert program['simulationCorrections'] == [first, second]


def test_audit_document_is_detached_from_caller_mutation():
    model = project('A:=1;', [variable('A')])
    document = {'schemaVersion': 1, 'corrections': [correction(model, 'A:=1;', 'A:=2;')]}
    apply_corrections(model, document)
    document['corrections'][0]['reason'] = 'Changed outside the workspace'
    assert model['sourceCorrections']['corrections'][0]['reason'] == 'Explicit fixture correction'
    assert model['programs'][0]['simulationCorrection']['reason'] == 'Explicit fixture correction'
