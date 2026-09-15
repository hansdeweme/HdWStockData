"""Export project Python sources: python tools/py_sources_to_txt.py OUTPUT."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sources = sorted(path for folder in ('hdw_stock_data', 'examples', 'tests', 'tools')
                     for path in (root / folder).glob('*.py'))
    # Exclusive creation prevents overwriting an existing file or a source file.
    with args.output.open('x', encoding='utf-8') as output:
        for path in sources:
            name = path.relative_to(root).as_posix()
            output.write(f'--- Start of {name} ---\n')
            output.write(path.read_text(encoding='utf-8'))
            output.write(f'\n--- End of {name} ---\n\n')


if __name__ == '__main__':
    main()
