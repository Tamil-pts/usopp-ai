"""Comprehensive test suite for Chopper Command Layer (Phase 1 through Phase 5)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['USOPP_CHOPPER_ACTIONS'] = '1'

from backend.core.chopper_actions.registry import match_action, get_action, all_actions
from backend.core.chopper_actions.router import reply_if_action
from backend.core.chopper_actions.plan_security import (
    sign_plan, verify_plan, consume_plan, plan_hash, _USED_PLANS, _USED_PLANS_LOCK
)
from backend.core.chopper_actions.permissions import (
    user_has_permission, module_permitted, save_config, read_config
)
from backend.core.chopper_actions.actions.bytecheck import _summarize as summarize_bytecheck
from backend.core.chopper_actions.actions.matchview import _summarize as summarize_matchview
from backend.core.chopper_actions.actions.project_pack import _summarize as summarize_project_pack
from backend.core.chopper_actions.actions.create_frd import _summarize as summarize_create_frd
from backend.core.chopper_actions.actions.create_mom import _summarize as summarize_create_mom
from backend.core.chopper_actions.actions.create_quality_report import _summarize as summarize_create_quality_report


class TestChopperActionsSecurity(unittest.TestCase):
    def setUp(self):
        with _USED_PLANS_LOCK:
            _USED_PLANS.clear()
        self.user_id = 'test_engineer'
        self.action_id = 'bytecheck'
        self.slots = {'project_path': 'C:/Test/Project', 'machine_department': 'Carding'}

    def test_plan_signing_and_verification(self):
        sig, expiry = sign_plan(self.user_id, self.action_id, self.slots)
        p_hash = plan_hash(self.user_id, self.action_id, self.slots, expiry)
        
        # Valid verification
        err = verify_plan(self.user_id, self.action_id, self.slots, expiry, sig, p_hash)
        self.assertIsNone(err)

    def test_tampered_plan_rejected(self):
        sig, expiry = sign_plan(self.user_id, self.action_id, self.slots)
        p_hash = plan_hash(self.user_id, self.action_id, self.slots, expiry)
        
        # Tampered slots
        tampered_slots = dict(self.slots, machine_department='Finisher')
        err = verify_plan(self.user_id, self.action_id, tampered_slots, expiry, sig, p_hash)
        self.assertIsNotNone(err)
        self.assertIn('signature is invalid', err)

    def test_expired_plan_rejected(self):
        sig, _ = sign_plan(self.user_id, self.action_id, self.slots)
        p_hash = 'some_hash'
        expired_epoch = 1000  # long past
        err = verify_plan(self.user_id, self.action_id, self.slots, expired_epoch, sig, p_hash)
        self.assertIsNotNone(err)
        self.assertIn('expired', err)

    def test_consumed_plan_single_use(self):
        sig, expiry = sign_plan(self.user_id, self.action_id, self.slots)
        p_hash = plan_hash(self.user_id, self.action_id, self.slots, expiry)
        
        # Consume
        consume_plan(p_hash, expiry)
        
        # Re-verify should fail
        err = verify_plan(self.user_id, self.action_id, self.slots, expiry, sig, p_hash)
        self.assertIsNotNone(err)
        self.assertIn('already been used', err)


class TestChopperActionsPermissions(unittest.TestCase):
    def tearDown(self):
        save_config({'pilot_users': [], 'pilot_roles': []})

    def test_admin_allowed(self):
        admin = {'role': 'admin', 'username': 'superadmin'}
        self.assertTrue(user_has_permission(admin))

    def test_pilot_users_config(self):
        save_config({'pilot_users': ['lead_dev'], 'pilot_roles': ['lead']})
        
        pilot_user = {'role': 'engineer', 'username': 'lead_dev'}
        non_pilot = {'role': 'engineer', 'username': 'intern'}
        lead_role = {'role': 'lead', 'username': 'someone'}
        
        self.assertTrue(user_has_permission(pilot_user))
        self.assertTrue(user_has_permission(lead_role))
        self.assertFalse(user_has_permission(non_pilot))


class TestChopperCommandPhraseMatching(unittest.TestCase):
    """Test 30+ command phrases matching registered actions."""
    def test_30_command_phrases(self):
        commands = [
            # ByteCheck / Validation commands
            ('run bytecheck on this project', 'bytecheck'),
            ('start bytecheck', 'bytecheck'),
            ('execute validation for plc project', 'bytecheck'),
            ('perform bytemap validation', 'bytecheck'),
            ('validate this project', 'bytecheck'),
            ('validate plc code', 'bytecheck'),
            ('check plc project', 'bytecheck'),
            ('run validation', 'bytecheck'),
            ('launch bytecheck', 'bytecheck'),
            ('do bytemap check', 'bytecheck'),
            ('verify this project', 'bytecheck'),
            ('run a validation', 'bytecheck'),

            # MatchView / Comparison commands
            ('run matchview on these two projects', 'matchview'),
            ('compare base project and developed project', 'matchview'),
            ('start comparison in matchview', 'matchview'),
            ('compare base and developed plc', 'matchview'),
            ('launch matchview comparison', 'matchview'),
            ('diff between base and new version', 'matchview'),
            ('execute matchview', 'matchview'),
            ('do comparison of projects', 'matchview'),
            ('run compare projects', 'matchview'),
            ('start matchview', 'matchview'),
            ('difference between projects', 'matchview'),
            ('i have uploaded two project compare the both and summary me that result', 'matchview'),

            # Project Pack / Creation commands
            ('create a project', 'project_pack'),
            ('create new project', 'project_pack'),
            ('new project pack', 'project_pack'),
            ('setup project pack', 'project_pack'),
            ('build project with frd and mom', 'project_pack'),
            ('start a new project', 'project_pack'),
            ('create project pack', 'project_pack'),
            ('build project pack', 'project_pack'),
            ('Create an new project and FRD', 'project_pack'),

            # Specific Document Creation commands (FRD, MOM, Quality)
            ('create an frd', 'create_frd'),
            ('draft functional requirements', 'create_frd'),
            ('new frd document', 'create_frd'),
            ('create mom', 'create_mom'),
            ('record meeting minutes', 'create_mom'),
            ('create quality report', 'create_quality_report'),
            ('draft fat report', 'create_quality_report'),
            ('create validation report', 'create_quality_report'),
        ]
        self.assertGreaterEqual(len(commands), 30)
        for phrase, expected_action in commands:
            entry = match_action(phrase)
            self.assertIsNotNone(entry, f"Command phrase '{phrase}' failed to match any action")
            self.assertEqual(entry.id, expected_action, f"Phrase '{phrase}' matched {entry.id}, expected {expected_action}")


class TestChopperQuestionPhraseFallthrough(unittest.TestCase):
    """Test 30+ question phrases falling through unchanged to old Chopper (returning None)."""
    def test_30_question_phrases(self):
        questions = [
            'What is ByteCheck?',
            'How do I validate a project in ByteMap?',
            'Why did my validation fail on Group Code 10?',
            'Explain how to run validation',
            'Can you explain the difference between base and developed?',
            'Where can I find the metadata workbook?',
            'Tell me about the SpinConnect packet structure',
            'Show me the ladder diagram for mms_nw_rCyclic.st',
            'Describe how alarm receive timeout works',
            'Is there any communication failure in this capture?',
            'Does this project support Blow Room product code?',
            'Are there any syntax errors in this ST routine?',
            'Do I need to attach metadata to decode logs?',
            'Should I check Sheet2 mappings before running?',
            'Could you explain what changed in the PLC logic?',
            'Would you review this function block?',
            'Who created this project?',
            'When was the last validation executed?',
            'Which axes are configured in this machine?',
            'What changed between the two versions?',
            'How does RTC synchronization work in B&R?',
            'Why is variable mms_machine_status not found?',
            'Can you show me the HMI screen mappings?',
            'What is the purpose of this machine?',
            'How do I export comparison report to PDF?',
            'Why are there missing Sheet2 references?',
            'What does error CP-01 mean?',
            'Explain the interlock logic on line 45',
            'Can you explain the operating sequence?',
            'Where is the communication timeout handled?',
            'Tell me what is wrong with this log file',
        ]
        self.assertGreaterEqual(len(questions), 30)
        for q in questions:
            res = reply_if_action({'question': q})
            self.assertIsNone(res, f"Question phrase '{q}' must fall through to old Chopper (returned {res})")


class TestActionsEndToEnd(unittest.TestCase):
    """Test multi-turn slot collection, confirmation, and swap."""
    def setUp(self):
        with _USED_PLANS_LOCK:
            _USED_PLANS.clear()

    def test_matchview_swap_roundtrip(self):
        state = {
            'phase': 'confirm',
            'actionId': 'matchview',
            'slots': {'base_path': 'C:/Base', 'new_path': 'C:/Developed'},
            'signature': 'dummy',
            'expiry': 9999999999,
            'planHash': 'dummy'
        }
        with patch('backend.core.chopper_actions.router._current_user', return_value={'role': 'admin', 'username': 'admin'}):
            res = reply_if_action({'question': 'swap', '_actionState': state})
            self.assertIsNotNone(res)
            self.assertEqual(res['type'], 'action-plan')
            self.assertIn('Swapped', res.get('notice', ''))
            new_slots = res['_actionState']['slots']
            self.assertEqual(new_slots['base_path'], 'C:/Developed')
            self.assertEqual(new_slots['new_path'], 'C:/Base')

    def test_auto_assign_slots_from_two_attached_projects(self):
        payload = {
            'question': 'i have uploaded two project compare the both and summary me that result',
            'attachments': [
                {'kind': 'project', 'projectPath': 'C:/Projects/BaseProject'},
                {'kind': 'project', 'projectPath': 'C:/Projects/DevProject'}
            ]
        }
        with patch('backend.core.chopper_actions.router._current_user', return_value={'role': 'admin', 'username': 'admin'}):
            res = reply_if_action(payload)
            self.assertIsNotNone(res)
            # Since both base and new paths were provided, it directly builds the action plan card!
            self.assertEqual(res['type'], 'action-plan')
            self.assertEqual(res['actionId'], 'matchview')
            slots = res['_actionState']['slots']
            self.assertEqual(slots['base_path'], 'C:/Projects/BaseProject')
            self.assertEqual(slots['new_path'], 'C:/Projects/DevProject')

    def test_cancel_plan(self):
        state = {
            'phase': 'confirm',
            'actionId': 'bytecheck',
            'slots': {'project_path': 'C:/Test', 'machine_department': 'Carding'},
            'signature': 'dummy',
            'expiry': 9999999999,
            'planHash': 'dummy'
        }
        with patch('backend.core.chopper_actions.router._current_user', return_value={'role': 'admin', 'username': 'admin'}):
            res = reply_if_action({'question': 'cancel', '_actionState': state})
            self.assertIsNotNone(res)
            self.assertEqual(res['type'], 'action-cancelled')

    def test_project_pack_summarize(self):
        mock_result = {
            'projectId': 'PROJ-TEST-101',
            'title': 'HighSpeed Carding C1',
            'customer': 'SpinTech Mills',
            'department': 'Carding',
            'standards': 'CE',
            'documents': [
                {'kind': 'FRD', 'title': 'HighSpeed Carding C1 — FRD', 'status': 'Draft created'},
                {'kind': 'Flowchart', 'title': 'HighSpeed Carding C1 — Flowchart', 'status': 'Draft created'},
                {'kind': 'MoM', 'title': 'HighSpeed Carding C1 — MoM', 'status': 'Draft created'},
            ]
        }
        summary = summarize_project_pack(mock_result)
        self.assertEqual(summary['type'], 'action-summary')
        self.assertEqual(summary['actionId'], 'project_pack')
        self.assertEqual(summary['projectId'], 'PROJ-TEST-101')
        self.assertEqual(len(summary['documents']), 3)

    def test_create_frd_summarize(self):
        mock_result = {
            'scopeId': 'SCOPE-FRD-001',
            'docTitle': 'Motor Alarm Control',
            'documentNumber': 'PTPL-FRD-001',
            'customer': 'LMW',
            'department': 'Spinning',
            'scope': 'In scope: motor trip logic',
            'acceptanceCriteria': 'Response < 100ms',
            'requirements': [{'id': 'FR-001', 'title': 'Trip motor on overload'}],
            'requirementsCount': 1,
        }
        summary = summarize_create_frd(mock_result)
        self.assertEqual(summary['type'], 'action-summary')
        self.assertEqual(summary['actionId'], 'create_frd')
        self.assertEqual(summary['scopeId'], 'SCOPE-FRD-001')
        self.assertEqual(summary['requirementsCount'], 1)

    def test_create_mom_summarize(self):
        mock_result = {
            'scopeId': 'SCOPE-MOM-001',
            'meetingSubject': 'Kickoff Alignment',
            'docTitle': 'Kickoff Alignment — Minutes of Meeting',
            'documentNumber': 'PTPL-MOM-001',
            'customer': 'LMW',
            'department': 'Comber',
            'decisions': [{'decision': 'Use IEC 61131-3'}],
            'actions': [{'task': 'Review PLC logic', 'owner': 'Admin'}],
        }
        summary = summarize_create_mom(mock_result)
        self.assertEqual(summary['type'], 'action-summary')
        self.assertEqual(summary['actionId'], 'create_mom')
        self.assertEqual(summary['meetingSubject'], 'Kickoff Alignment')
        self.assertEqual(len(summary['decisions']), 1)

    def test_create_quality_report_summarize(self):
        mock_result = {
            'scopeId': 'SCOPE-FAT-001',
            'docTitle': 'FAT Validation Report',
            'documentNumber': 'PTPL-FAT-001',
            'customer': 'LMW',
            'department': 'General',
            'testScope': 'Safety interlocks',
            'acceptanceCriteria': 'Zero critical alarms',
            'cases': [{'id': 'TC-001', 'title': 'E-stop trip'}],
            'testCasesCount': 1,
        }
        summary = summarize_create_quality_report(mock_result)
        self.assertEqual(summary['type'], 'action-summary')
        self.assertEqual(summary['actionId'], 'create_quality_report')
        self.assertEqual(summary['testCasesCount'], 1)


if __name__ == '__main__':
    unittest.main()
