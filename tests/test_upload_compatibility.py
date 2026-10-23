"""Multipart limits belong to the request parser, not FastAPI's File schema."""
import ast
import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from backend.core import runtime


class UploadCompatibilityTests(unittest.TestCase):
    def test_routes_do_not_pass_parser_options_to_file(self):
        root=Path(__file__).resolve().parents[1]
        checked=0
        for directory in ('backend/api','virtual_plc'):
            for path in (root/directory).rglob('*.py'):
                for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='File':
                        checked+=1
                        self.assertNotIn('max_files',{item.arg for item in node.keywords},str(path))
        self.assertGreater(checked,10)

    def test_default_parser_keeps_large_automation_studio_upload_limits(self):
        request=object()
        original=AsyncMock(return_value='form')
        with patch.object(runtime,'_ORIGINAL_GET_FORM',original):
            self.assertEqual('form',asyncio.run(runtime._usopp_get_form(request)))
        original.assert_awaited_once_with(request,max_files=runtime.MAX_PROJECT_FILES,
                                          max_fields=runtime.MAX_PROJECT_FILES,max_part_size=100*1024*1024)

    def test_explicit_parser_count_limits_are_preserved(self):
        request=object()
        original=AsyncMock(return_value='form')
        with patch.object(runtime,'_ORIGINAL_GET_FORM',original):
            asyncio.run(runtime._usopp_get_form(request,max_files=12,max_fields=7,max_part_size=200*1024*1024))
        original.assert_awaited_once_with(request,max_files=12,max_fields=7,max_part_size=200*1024*1024)


if __name__=='__main__':unittest.main()
