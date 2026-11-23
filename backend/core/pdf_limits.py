"""Administrator-configurable limits for PDF drawings, electrical comparison, and e-design reviews."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path


def _get_config_path() -> Path:
    try:
        from backend.core.runtime import KNOWLEDGE
        return KNOWLEDGE / 'master' / 'pdf_drawing_limits.json'
    except Exception:
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])).resolve()
        base = Path(os.getenv('USOPP_DATA_ROOT') or root).resolve()
        return base / 'knowledge' / 'master' / 'pdf_drawing_limits.json'


DEFAULT_PDF_LIMITS = {
    'version': '1.0',
    'maxPages': 10000,
    'maxFileSizeMB': 500,
}

_CACHE = None
_CACHE_MTIME = 0


def read_pdf_limits() -> dict:
    global _CACHE, _CACHE_MTIME
    config_file = _get_config_path()
    try:
        if config_file.is_file():
            mtime = config_file.stat().st_mtime
            if _CACHE is not None and mtime == _CACHE_MTIME:
                return dict(_CACHE)
            data = json.loads(config_file.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'maxPages' in data:
                _CACHE = {
                    'version': '1.0',
                    'maxPages': max(1, min(100000, int(data.get('maxPages') or 10000))),
                    'maxFileSizeMB': max(10, min(2048, int(data.get('maxFileSizeMB') or 500))),
                }
                _CACHE_MTIME = mtime
                return dict(_CACHE)
    except (OSError, ValueError):
        pass
    return dict(DEFAULT_PDF_LIMITS)


def get_pdf_page_limit() -> int:
    return read_pdf_limits()['maxPages']


def get_pdf_max_bytes() -> int:
    return read_pdf_limits()['maxFileSizeMB'] * 1024 * 1024


def save_pdf_limits(payload: dict) -> dict:
    global _CACHE, _CACHE_MTIME
    if not isinstance(payload, dict):
        raise ValueError('Invalid payload format.')
    try:
        pages = int(payload.get('maxPages', 10000))
    except (ValueError, TypeError):
        raise ValueError('Max pages must be an integer between 1 and 100,000.')
    if not 1 <= pages <= 100000:
        raise ValueError('Max pages must be between 1 and 100,000.')

    try:
        size_mb = int(payload.get('maxFileSizeMB', 500))
    except (ValueError, TypeError):
        raise ValueError('Max file size must be an integer between 10 and 2048 MB.')
    if not 10 <= size_mb <= 2048:
        raise ValueError('Max file size must be between 10 and 2,048 MB.')

    result = {
        'version': '1.0',
        'maxPages': pages,
        'maxFileSizeMB': size_mb,
    }
    config_file = _get_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    _CACHE = dict(result)
    _CACHE_MTIME = config_file.stat().st_mtime
    return result

