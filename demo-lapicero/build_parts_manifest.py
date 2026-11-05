"""Build the browser's part-position manifest from Blender-exported GLBs."""
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read_node_positions(filename):
    data = filename.read_bytes()
    if len(data) < 20 or struct.unpack_from('<I', data, 0)[0] != 0x46546C67:
        raise ValueError(f'Not a valid GLB file: {filename}')
    json_length = struct.unpack_from('<I', data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    return {
        node['name']: node.get('translation', [0, 0, 0])
        for node in document.get('nodes', [])
        if node.get('name')
    }


def main():
    assembled = read_node_positions(HERE / 'lapicero.glb')
    exploded = read_node_positions(HERE / 'lapicero-exploded.glb')
    parts = [
        {'nodeName': name, 'originPosition': position, 'explodedPosition': exploded[name]}
        for name, position in assembled.items()
        if name in exploded
    ]
    manifest = {
        'modelId': 'lapicero',
        'source': 'Positions derived from lapicero.glb and lapicero-exploded.glb',
        'parts': parts,
    }
    target = HERE / 'lapicero-parts.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(parts)} mesh positions to {target}')


if __name__ == '__main__':
    main()
