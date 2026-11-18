"""Exercise real review components using an actual packet-engine JSON result.

Isolated local fixture only: no production data, accounts or PLC connections.
Run node scripts/check_result_evidence.mjs --browser-fixture before this script.
"""
import csv
import io
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_packet_response_controls import ENGINE, write_project
from playwright.sync_api import sync_playwright

out = ROOT / '.build/result-evidence-review'
out.mkdir(parents=True, exist_ok=True)
project = out / 'engine-project'
write_project(project)
result = ENGINE.run_engine_json(project, output_excel_path=out / 'engine-report.xlsx')
(out / 'engine-result.json').write_text(json.dumps(result, default=str), encoding='utf-8')

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(out)))
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
        review = page.get_by_role('region', name='ByteMap evidence review', exact=True)
        review.wait_for()
        assert review.locator('.resultReviewList details').count() > 0
        review.get_by_label('Search ByteMap findings').fill('Packet Overflow')
        assert review.locator('.resultReviewList details').count() == 1
        review.locator('summary').click()
        issue = next(i for i in result['issues'] if i['validationType'] == 'Packet Overflow')
        assert issue['suggestedFix'] in review.inner_text()
        review.get_by_role('button', name='Open reported source', exact=True).click()
        assert page.get_by_label('Selected evidence source').inner_text() == f"{issue['sourceFile']}:{issue['lineNumber']}"
        with page.expect_download() as download_info:
            review.get_by_role('button', name='Export findings CSV', exact=True).click()
        download = download_info.value
        csv_path = out / download.suggested_filename
        download.save_as(csv_path)
        records = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding='utf-8'))))
        assert len(records) == 1
        assert records[0]['Expected'] == str(issue['expected'])
        assert records[0]['Actual'] == str(issue['actual'])
        assert records[0]['Status'] == issue['severity']
        assert records[0]['Recommendation'] == issue['suggestedFix']
        review.get_by_label('Search ByteMap findings').fill('')
        for width in (1440, 760, 390):
            page.set_viewport_size({'width': width, 'height': 900})
            for theme in ('light', 'dark'):
                page.evaluate('(t)=>document.documentElement.dataset.theme=t', theme)
                review.scroll_into_view_if_needed()
                assert review.evaluate('e=>e.scrollWidth <= e.clientWidth + 2')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                button = review.get_by_role('button', name='Export findings CSV', exact=True)
                button.scroll_into_view_if_needed()
                box = button.bounding_box()
                assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1
                page.screenshot(path=str(out / f'bytemap-{width}-{theme}.png'))
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.get_by_role('button', name='LogicScan fixture', exact=True).click()
        review = page.get_by_role('region', name='LogicScan evidence review', exact=True)
        assert review.locator('.resultReviewList details').count() == 2
        assert 'C70 target check' not in review.inner_text()
        assert 'Optional library' not in review.inner_text()
        review.get_by_role('combobox').select_option('all')
        assert review.locator('.resultReviewList details').count() == 4
        review.get_by_label('Search LogicScan findings').fill('T30')
        assert review.locator('.resultReviewList details').count() == 1
        assert page.get_by_text('Inspect the T30 binding in its own active configuration.', exact=True).count() >= 1
        review.get_by_label('Search LogicScan findings').fill('')
        for width in (1440, 760, 390):
            page.set_viewport_size({'width': width, 'height': 900})
            review.scroll_into_view_if_needed()
            assert review.evaluate('e=>e.scrollWidth <= e.clientWidth + 2')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
            page.screenshot(path=str(out / f'logicscan-{width}.png'))
        assert not errors, errors
        browser.close()
        (out / 'browser-results.json').write_text(json.dumps({'engineIssues': len(result['issues']), 'screenshots': 9, 'csvRows': len(records), 'pageErrors': errors}, indent=2))
        print('Browser passed: actual engine findings, exact CSV/source, filters, two themes, three widths and preserved rule guidance.')
finally:
    server.shutdown()
    server.server_close()
