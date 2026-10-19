"""Offline source release allowlist, fingerprint, and ZIP export. No Git operations."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

MANIFEST = 'release_manifest.json'
ALLOWLIST = 'release_allowlist.txt'
ROOT_FILES = {
    '.gitignore', 'README.md', 'REPRODUCING.md', 'TEST_RESULTS.md',
    'CODE_PROVENANCE.md', 'DATA_AND_THIRD_PARTY.md', 'ENVIRONMENT.md',
    'LICENSE', 'RELEASE_POLICY.md', 'pyproject.toml',
    'requirements-runtime.txt', 'requirements-build.txt', ALLOWLIST, MANIFEST,
}
PATTERNS = {
    'private-key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'token': r'(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})',
    'credential-assignment': r'''(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|secret[_-]?key)\s*[:=]\s*["'][^"'\n]{6,}''',
    'personal-path': r'/(?:Users|home)/[^/\s"\x27]+',
}


def checked_path(root, name):
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or str(rel) != name or '\\' in name:
        raise ValueError('Noncanonical or escaping release path')
    parts = rel.parts
    allowed = name in ROOT_FILES
    if len(parts) == 2 and parts[0] in ('docs', 'scripts', 'tests'):
        allowed = rel.suffix == ('.md' if parts[0] == 'docs' else '.py')
    if len(parts) == 3 and parts[:2] == ('src', 'futures_factor'):
        allowed = rel.suffix == '.py'
    allowed |= name in ('data/README.md', 'reports/platform_reported.md')
    if not allowed:
        raise ValueError(f'Excluded material cannot be released: {name}')
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Symlink prohibited: {name}')
    if not path.is_file():
        raise ValueError(f'Missing release file: {name}')
    return path


def names(root):
    path = root / ALLOWLIST
    if path.is_symlink():
        raise ValueError('Symlink allowlist prohibited')
    rows = path.read_text(encoding='utf-8').splitlines()
    result = [s for s in rows if s and not s.startswith('#')]
    if result != sorted(set(result)) or not {ALLOWLIST, MANIFEST} <= set(result):
        raise ValueError('Allowlist must be sorted, unique and include itself and manifest')
    return result


def scan(name, content):
    try:
        text = content.decode('utf-8')
    except UnicodeError as exc:
        raise ValueError(f'Non-text release material: {name}') from exc
    for label, pattern in PATTERNS.items():
        if re.search(pattern, text):
            # Never echo secret contents in diagnostics.
            raise ValueError(f'Sensitive content pattern ({label}): {name}')


def payload(root, refresh=False):
    result = {}
    for name in names(root):
        if name == MANIFEST and refresh:
            continue
        content = checked_path(root, name).read_bytes()
        scan(name, content)
        result[name] = content
    return result


def refresh_manifest(root):
    files = payload(root, refresh=True)
    dest = root / MANIFEST
    if dest.is_symlink():
        raise ValueError('Symlink manifest prohibited')
    document = {'schema': 1, 'scope': 'research-framework-source-only',
                'self_hash_excluded': MANIFEST,
                'files': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    dest.write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def verify(root):
    files = payload(root)
    document = json.loads(files[MANIFEST])
    expected = {n: hashlib.sha256(b).hexdigest() for n, b in files.items() if n != MANIFEST}
    if (document.get('schema') != 1 or document.get('scope') != 'research-framework-source-only'
        or document.get('self_hash_excluded') != MANIFEST or document.get('files') != expected):
        raise ValueError('Manifest file set or SHA256 mismatch')
    return files


def export(root, output):
    files = verify(root)
    if output.is_symlink() or output.resolve() in {(root/n).resolve() for n in files}:
        raise ValueError('Export must not overwrite release sources')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--verify', action='store_true')
    actions.add_argument('--refresh-manifest', action='store_true')
    actions.add_argument('--export', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.refresh_manifest:
            refresh_manifest(root)
            print('Manifest refreshed; this is not a rights or secrecy certification.')
        elif args.export:
            count = export(root, args.export)
            print(f'Exported {count} allowlisted text files.')
        else:
            print(f'Verified {len(verify(root))} allowlisted text files.')
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Release rejected: {exc}\n')


if __name__ == '__main__':
    main()
