#!/usr/bin/env python3
"""Rebuild published fragments from a matching local ima installation; no network."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=Path.home() / 'Library/Application Support/com.tencent.imamac')
    parser.add_argument('--source-dir', type=Path, help='Directory containing the relative_paths in the source manifest, instead of a live profile')
    parser.add_argument('--output', type=Path, default=ROOT / '_local/rebuilt')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'evidence/source-manifest.json').read_text())
    inputs = {}
    for source in manifest['sources']:
        base = args.source_dir if args.source_dir else args.profile
        file = base / source['relative_path']
        if not file.is_file():
            raise SystemExit(f'Missing matching source: {file}\nA different ima version is not evidence for this manifest.')
        data = file.read_bytes()
        if digest(data) != source['sha256'] or len(data) != source['byte_length']:
            raise SystemExit(f'Identity mismatch: {source["id"]}; do not silently substitute a different version.')
        inputs[source['id']] = data.decode('utf-8')
    for fragment in manifest['fragments']:
        text = inputs[fragment['source_id']]
        selector = fragment['selector']
        start = text.index(selector['start_marker']) + (len(selector['start_marker']) if selector['exclude_start_marker'] else 0)
        end = text.index(selector['end_marker'], start) if selector['end_marker'] is not None else start + selector['length_code_points']
        selected = text[start:end]
        data = selected.encode('utf-8')
        offsets = {
            'code_point_start': start, 'code_point_end': end,
            'utf16_start': len(text[:start].encode('utf-16-le')) // 2,
            'utf16_end': len(text[:end].encode('utf-16-le')) // 2,
            'utf8_byte_start': len(text[:start].encode('utf-8')),
            'utf8_byte_end': len(text[:end].encode('utf-8')),
        }
        if offsets != fragment['offsets'] or digest(data) != fragment['sha256']:
            raise SystemExit(f'Extraction mismatch: {fragment["id"]}')
        output = args.output / fragment['path']
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    receipt = {
        'source_ids': [source['id'] for source in manifest['sources']],
        'fragment_ids': [fragment['id'] for fragment in manifest['fragments']],
        'all_parent_hashes_match': True, 'all_fragment_bytes_and_offsets_match': True,
        'network_used': False,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'extraction-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Rebuilt and byte-verified {len(manifest["fragments"])} fragments in {args.output}')


if __name__ == '__main__':
    main()
