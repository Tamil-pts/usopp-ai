"""Test dynamic PDF drawing page and file size limits across Circuit Compare, E-Design and Admin Settings."""
import json
import pytest
from backend.core import pdf_limits


def test_pdf_limits_defaults_and_save(tmp_path, monkeypatch):
    test_config = tmp_path / 'pdf_drawing_limits.json'
    monkeypatch.setattr(pdf_limits, '_get_config_path', lambda: test_config)
    pdf_limits._CACHE = None
    pdf_limits._CACHE_MTIME = 0

    # Default values
    assert pdf_limits.get_pdf_page_limit() == 10000
    assert pdf_limits.get_pdf_max_bytes() == 500 * 1024 * 1024

    # Save custom limit
    saved = pdf_limits.save_pdf_limits({'maxPages': 25000, 'maxFileSizeMB': 1024})
    assert saved['maxPages'] == 25000
    assert saved['maxFileSizeMB'] == 1024
    assert pdf_limits.get_pdf_page_limit() == 25000
    assert pdf_limits.get_pdf_max_bytes() == 1024 * 1024 * 1024

    # Validation errors
    with pytest.raises(ValueError):
        pdf_limits.save_pdf_limits({'maxPages': 0})
    with pytest.raises(ValueError):
        pdf_limits.save_pdf_limits({'maxPages': 200000})
    with pytest.raises(ValueError):
        pdf_limits.save_pdf_limits({'maxFileSizeMB': 5})
    with pytest.raises(ValueError):
        pdf_limits.save_pdf_limits({'maxFileSizeMB': 5000})
