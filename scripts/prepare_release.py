"""Validate the stable manifest version and extract its changelog notes."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def release_details(root):
    version = json.loads((root / 'custom_components/echo_experience/manifest.json').read_text())['version']
    if not isinstance(version, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('The manifest must contain a stable major.minor.patch version')
    sections = re.split(r'^##\s+', (root / 'CHANGELOG.md').read_text(), flags=re.MULTILINE)[1:]
    matching = [s for s in sections if re.match(re.escape(version) + r'(?=\s|$)', s)]
    if len(matching) != 1:
        raise ValueError('Exactly one changelog section is required for ' + version)
    _, separator, notes = matching[0].partition('\n')
    if not separator or not notes.strip():
        raise ValueError('Release notes must not be empty')
    return version, notes.strip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    version, notes = release_details(ROOT)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'version.txt').write_text(version + '\n')
    (args.output_dir / 'notes.md').write_text(notes)
    print('Prepared release v' + version)


if __name__ == '__main__':
    main()
