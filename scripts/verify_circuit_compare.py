"""Reproduce a drawing comparison without modifying the originals or PLC engines.

python scripts/verify_circuit_compare.py --base base.pdf --developed corrected.pdf --output .build/circuit-check
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_engine.circuit_compare import compare_drawings
from python_engine.circuit_report import build_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--developed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def progress(phase, current, total):
        if current in (1, total): print(f'{phase}: {current}/{total}', flush=True)
    result = compare_drawings(args.base, args.developed, args.output, progress=progress)
    build_report(result, args.output, args.output / 'Circuit_Comparison.pdf')
    print(json.dumps(result['summary'], indent=2))
    print('Review the JSON change register, original page previews and Circuit_Comparison.pdf together.')


if __name__ == '__main__': main()
