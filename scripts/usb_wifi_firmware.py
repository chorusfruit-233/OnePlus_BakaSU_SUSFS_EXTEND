#!/usr/bin/env python3
"""Collect USB-driver firmware and stage actual, uncompressed built-in blobs.

Only explicitly selected USB source files and their local headers are scanned.
linux-firmware is read at a pinned commit; WHENCE aliases are materialized under
the exact names the kernel requests. Missing firmware is reported independently
of transfer, integrity, path and licensing errors, which always fail the build.
"""
import ast
import base64
from email.utils import parsedate_to_datetime
import fnmatch
import gzip
import hashlib
import io
import json
import lzma
import posixpath
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / 'profiles/usb-wifi-firmware.json'
STRING = re.compile(r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*')
COMMENT = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|/\*.*?\*/|//[^\n]*', re.S)


def safe_name(name, *, pattern=False):
    """Accept relative firmware names, never shell/Kconfig metacharacters."""
    if not isinstance(name, str) or not name or name.startswith('/') or '\\' in name:
        raise ValueError(f'unsafe firmware path: {name!r}')
    allowed = r'[A-Za-z0-9_.,/+@:-]+' if not pattern else r'[A-Za-z0-9_.,/+@:*?\[\]-]+'
    if not re.fullmatch(allowed, name) or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError(f'unsafe firmware path: {name!r}')
    return name


def _metadata_name(name):
    # WHENCE also contains unrelated firmware names with spaces (DMI board
    # names). Parse their provenance without putting those names in Kconfig.
    if (not isinstance(name, str) or not name or name.startswith('/') or
            any(c in name for c in ('\\', '\0', '\r', '\n')) or
            any(p in ('', '.', '..') for p in name.split('/'))):
        raise ValueError(f'unsafe firmware metadata path: {name!r}')
    return name


def destination(root, name):
    safe_name(name)
    root = Path(root).resolve()
    path = root / name
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'firmware path escapes destination: {name}')
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f'firmware destination contains a symlink: {part}')
    return path


def _without_comments(text):
    return COMMENT.sub(lambda m: m[1] or '', text).replace('\\\n', '')


def _expressions(text, name):
    """Read balanced macro/function arguments without matching comments."""
    for match in re.finditer(r'\b' + re.escape(name) + r'\s*\(', text):
        start = match.end()
        depth, quote, escaped = 1, None, False
        for i in range(start, len(text)):
            char = text[i]
            if quote:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in ('"', "'"):
                quote = char
            elif char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0:
                    yield text[start:i].strip()
                    break


def _string(expression, definitions, seen=()):
    expression = expression.strip()
    while expression.startswith('(') and expression.endswith(')'):
        expression = expression[1:-1].strip()
    tokens = STRING.findall(expression)
    if not tokens or STRING.sub('', expression).strip():
        return None
    result = ''
    for token in tokens:
        if token.startswith('"'):
            try:
                result += ast.literal_eval(token)
            except (ValueError, SyntaxError):
                return None
        else:
            if token in seen or token not in definitions:
                return None
            value = _string(definitions[token], definitions, seen + (token,))
            if value is None:
                return None
            result += value
    return result


def _source_files(source, paths):
    source = Path(source).resolve()
    pending, found = [], set()
    for relative in paths:
        safe_name(relative)
        candidate = source / relative
        if not candidate.resolve().is_relative_to(source):
            raise ValueError(f'driver source escapes kernel tree: {relative}')
        if candidate.is_file():
            pending.append(candidate)
        elif candidate.is_dir():
            pending.extend(p for p in candidate.rglob('*') if p.suffix in ('.c', '.h'))
    while pending:
        path = pending.pop().resolve()
        if path in found:
            continue
        if not path.resolve().is_relative_to(source):
            raise ValueError(f'driver header escapes kernel tree: {path}')
        found.add(path)
        # Resolve only local quoted includes, never traverse unrelated vendors.
        for header in re.findall(r'^\s*#\s*include\s*"([^"]+)"', path.read_text(errors='replace'), re.M):
            target = path.parent / header
            if target.is_file():
                pending.append(target)
    return sorted(found)


def collect_firmware(source, drivers):
    """Return requirements by enabled driver; preserve unresolved metadata.

    Catalog firmware entries supplement dynamic filenames and old trees missing
    MODULE_FIRMWARE declarations. Empty firmware + no requests means that driver
    uses no external firmware, only when its source files were actually found.
    """
    source = Path(source).resolve()
    result = {'drivers': {}, 'files': {}, 'unresolved': []}
    for driver in drivers:
        symbol = driver['symbol']
        paths = _source_files(source, driver.get('sources', []))
        texts = [_without_comments(p.read_text(errors='replace')) for p in paths]
        definitions = {}
        for text in texts:
            definitions.update(re.findall(r'^\s*#\s*define\s+(\w+)[ \t]+([^\n]+)', text, re.M))
            definitions.update(re.findall(r'\b(?:const\s+)?char\s*(?:\*\s*|\s+)(\w+)\s*(?:\[\s*\])?\s*=\s*([^;]+);', text))
        names = set(driver.get('firmware', []))
        for name in names:
            safe_name(name, pattern=True)
        unresolved = []
        declarations = [] if driver.get('firmware_only') else [
            expr for text in texts for expr in _expressions(text, 'MODULE_FIRMWARE')]
        requests = []
        for text in ([] if driver.get('firmware_only') else texts):
            for function in ('request_firmware', 'request_firmware_direct', 'request_firmware_nowarn',
                             'firmware_request_nowarn', 'request_firmware_into_buf',
                             'request_ihex_firmware', 'request_firmware_nowait'):
                for expression in _expressions(text, function):
                    args = expression.split(',')
                    index = 2 if function == 'request_firmware_nowait' else 1
                    if len(args) > index:
                        requests.append(args[index].strip())
        for expression in declarations + requests:
            name = _string(expression, definitions)
            if name:
                names.add(safe_name(name))
            elif expression in declarations or not declarations:
                unresolved.append(expression)
        requested_names = {_string(expression, definitions) for expression in requests}
        # Explicit catalog fallback documents filenames constructed at runtime;
        # retain the expression as evidence without treating it as a missing blob.
        fallback = bool(driver.get('firmware'))
        # ath6kl MODULE_FIRMWARE lists fw.ram.bin as well as full board paths;
        # its loader joins the hardware directory at runtime. The catalog's
        # directory pattern covers those names, so do not request a bogus blob
        # in the firmware root when the same basename has a known full path.
        for name in list(names):
            if '/' not in name and name not in requested_names and any(posixpath.dirname(pattern) and
                    fnmatch.fnmatchcase(name, posixpath.basename(pattern))
                    for pattern in driver.get('firmware', [])):
                names.remove(name)
                unresolved.append(name + ' (joined with catalog hardware directory)')
        active_unresolved = [] if fallback else sorted(set(unresolved))
        if not paths:
            active_unresolved.append('no catalog source files found')
        record = {'files': sorted(names), 'sources': [str(p.relative_to(source)) for p in paths],
                  'unresolved': active_unresolved, 'catalog_resolved': sorted(set(unresolved)) if fallback else [],
                  'no_firmware': bool(paths) and not names and not active_unresolved}
        result['drivers'][symbol] = record
        result['unresolved'].extend({'driver': symbol, 'reference': expr} for expr in active_unresolved)
        for name in names:
            result['files'].setdefault(name, []).append(symbol)
    for drivers_for_file in result['files'].values():
        drivers_for_file.sort()
    return result


def parse_whence(text):
    records, links = {}, {}
    for block in re.split(r'^-{3,}\s*$', text, flags=re.M):
        entries = []
        for kind, raw in re.findall(r'^(File|RawFile|Link):\s*(.+)$', block, re.M):
            if kind == 'Link':
                name, target = raw.split(' -> ', 1)
                name = _metadata_name(re.sub(r'\\(.)', r'\1', name.strip().strip('"')))
                target = re.sub(r'\\(.)', r'\1', target.strip().strip('"'))
                if target.startswith('/') or '\\' in target:
                    raise ValueError(f'unsafe WHENCE link: {raw}')
                target = _metadata_name(posixpath.normpath(posixpath.join(posixpath.dirname(name), target)))
                links[name] = target
            else:
                name = _metadata_name(re.sub(r'\\(.)', r'\1', raw.strip().strip('"')))
            entries.append(name)
        if not entries:
            continue
        licence = re.search(r'^Licen[cs]e:\s*(.*)', block, re.M)
        # The whole stanza is kept, including inline license/redistribution terms.
        references = sorted(set(re.findall(r'\b(?:LICEN[CS]E[.\w+-]+|NOTICE[.\w+-]+|GPL-\d\.\d|Apache-\d\.\d)\b', block)))
        record = {'whence': block.strip() + '\n', 'license': licence[1].strip() if licence else '',
                  'license_files': references}
        for name in entries:
            records[name] = record
    return records, links


def _blob_hash(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def _tree_hash(entries):
    data = bytearray()
    for entry in sorted(entries, key=lambda item: (item['name'] + ('/' if item['type'] == 'tree' else '')).encode()):
        name = _metadata_name(entry['name'])
        if '/' in name or not re.fullmatch(r'[0-9a-f]{40}', entry['id']):
            raise ValueError('invalid firmware Git tree entry')
        mode = int(entry['mode'], 8) if isinstance(entry['mode'], str) else int(entry['mode'])
        data.extend(f'{mode:o} {name}\0'.encode() + bytes.fromhex(entry['id']))
    return hashlib.sha1(f'tree {len(data)}\0'.encode() + data).hexdigest()


class FirmwareRepository:
    """Read a single fixed Gitiles revision, validating cached Git blobs."""
    def __init__(self, lock, cache_dir=None):
        self.repository = lock['repository'].rstrip('/')
        self.revision = lock['revision']
        if not re.fullmatch(r'[0-9a-f]{40}', self.revision):
            raise ValueError('firmware revision must be a full immutable Git commit SHA')
        if not self.repository.startswith('https://'):
            raise ValueError('firmware repository must use HTTPS')
        self.cache = Path(cache_dir).resolve() / self.revision if cache_dir else None
        self.root_tree = lock.get('root_tree')
        if self.root_tree and not re.fullmatch(r'[0-9a-f]{40}', self.root_tree):
            raise ValueError('firmware root tree must be a full immutable Git object ID')
        self.trees = {}

    def _fetch(self, relative, format):
        url = f'{self.repository}/+/{self.revision}/{urllib.parse.quote(relative, safe="/")}?format={format}'
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read()
                break
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 404:
                    raise FileNotFoundError(relative) from error
                if attempt < 3 and (error.code == 429 or 500 <= error.code < 600):
                    delay = (2, 5, 10)[attempt]
                    retry_after = error.headers.get('Retry-After') if error.headers else None
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            try:
                                delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
                            except (TypeError, ValueError, OverflowError):
                                pass
                    time.sleep(max(0, min(10, delay)))
                    continue
                raise ValueError(f'firmware download failed ({url}): HTTP {error.code}') from error
            except (OSError, urllib.error.URLError) as error:
                raise ValueError(f'firmware download failed ({url}): {error}') from error
        try:
            if format == 'TEXT':
                return base64.b64decode(data, validate=True)
            if not data.startswith(b")]}'\n"):
                raise ValueError('not a Gitiles JSON response')
            return json.loads(data[5:])
        except (ValueError, TypeError) as error:
            raise ValueError(f'invalid firmware source response ({url}): {error}') from error

    def _checked_tree(self, directory, expected):
        if directory in self.trees:
            return self.trees[directory]
        cache = destination(self.cache, f'trees/{expected}.json') if self.cache else None
        if cache and cache.exists():
            try:
                entries = json.loads(cache.read_text())
            except (ValueError, TypeError) as error:
                raise ValueError(f'invalid firmware tree cache: {directory}') from error
        else:
            entries = self._fetch(directory + '/', 'JSON')['entries']
        try:
            actual = _tree_hash(entries)
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f'invalid firmware Git tree: {directory}') from error
        if actual != expected:
            raise ValueError(f'firmware Git tree checksum mismatch: {directory or "/"}')
        if cache and not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(entries, ensure_ascii=False) + '\n')
        self.trees[directory] = entries
        return entries

    def _directory(self, directory):
        if directory in self.trees:
            return self.trees[directory]
        if not self.root_tree:
            # Unpinned tree metadata is supported for older fixture locks, but
            # is never persisted as an authoritative reusable cache.
            entries = self._fetch(directory + '/', 'JSON')['entries']
            self.trees[directory] = entries
            return entries
        entries = self._checked_tree('', self.root_tree)
        parent = ''
        for component in directory.split('/') if directory else []:
            entry = next((item for item in entries if item['name'] == component and item['type'] == 'tree'), None)
            if not entry:
                raise FileNotFoundError(directory)
            parent = posixpath.join(parent, component)
            entries = self._checked_tree(parent, entry['id'])
        return entries

    def read(self, name):
        _metadata_name(name)
        directory, basename = posixpath.split(name)
        entry = next((e for e in self._directory(directory) if e['name'] == basename), None)
        if not entry or entry['type'] != 'blob':
            raise FileNotFoundError(name)
        oid = entry['id']
        if not re.fullmatch(r'[0-9a-f]{40}', oid):
            raise ValueError(f'invalid firmware Git object ID: {name}')
        cache_path = destination(self.cache, oid) if self.cache else None
        data = cache_path.read_bytes() if cache_path and cache_path.exists() else self._fetch(name, 'TEXT')
        if _blob_hash(data) != oid:
            raise ValueError(f'firmware Git blob checksum mismatch: {name}')
        if cache_path and not cache_path.exists():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)
        return data, entry.get('mode', 0)


def _read_blob(repository, name, links, seen=()):
    _metadata_name(name)
    if name in seen:
        raise ValueError(f'firmware link cycle: {name}')
    if name in links:
        return _read_blob(repository, links[name], links, seen + (name,))
    for suffix in ('', '.xz', '.zst', '.gz'):
        try:
            data, mode = repository.read(name + suffix)
        except FileNotFoundError:
            continue
        if mode in (0o120000, '120000'):
            target = data.decode().strip()
            if target.startswith('/') or '\\' in target:
                raise ValueError(f'unsafe firmware symlink: {name}')
            target = _metadata_name(posixpath.normpath(posixpath.join(posixpath.dirname(name), target)))
            return _read_blob(repository, target, links, seen + (name,))
        actual_name = name + suffix
        if actual_name.endswith('.xz'):
            data = lzma.decompress(data)
        elif actual_name.endswith('.gz'):
            data = gzip.decompress(data)
        elif actual_name.endswith('.zst'):
            executable = shutil.which('zstd')
            if not executable:
                raise ValueError(f'zstd is required to decompress firmware: {name}')
            process = subprocess.run([executable, '-d', '-q', '-c'], input=data, capture_output=True)
            if process.returncode:
                raise ValueError(f'cannot decompress firmware: {name}')
            data = process.stdout
        if not data:
            raise ValueError(f'empty firmware blob: {name}')
        return data, actual_name
    raise FileNotFoundError(name)


def _license_files(repository, record, metadata_dir, retained):
    if not record['license']:
        raise ValueError('firmware WHENCE stanza lacks license information')
    result = []
    for reference in record['license_files']:
        safe_name(reference)
        if reference not in retained:
            for candidate in (f'LICENSES/{reference}', reference):
                try:
                    data, _ = repository.read(candidate)
                    break
                except FileNotFoundError:
                    continue
            else:
                raise ValueError(f'firmware license text missing: {reference}')
            output = destination(metadata_dir, f'licenses/{reference}')
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            retained[reference] = {'name': reference, 'source_path': candidate,
                                   'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        result.append(reference)
    return result


def _archive_source(entry, metadata_dir, cache_dir):
    """Read a checksummed upstream archive without extracting arbitrary paths."""
    expected = entry['sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or not entry['url'].startswith('https://'):
        raise ValueError('supplemental firmware requires HTTPS and a pinned SHA256')
    cache = destination(cache_dir, f'archives/{expected}') if cache_dir else None
    if cache and cache.exists():
        data = cache.read_bytes()
    else:
        try:
            with urllib.request.urlopen(entry['url'], timeout=60) as response:
                data = response.read()
        except (OSError, urllib.error.URLError) as error:
            raise ValueError(f'supplemental firmware download failed ({entry["url"]}): {error}') from error
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'supplemental firmware archive checksum mismatch: {entry["name"]}')
    if cache and not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    # The complete original archive includes GPL source headers and notices.
    output = destination(metadata_dir, f'sources/{entry["archive_name"]}')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    members = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        for member in archive.getmembers():
            safe_name(member.name.rstrip('/'))
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f'supplemental firmware archive contains a link/special file: {member.name}')
            members[member.name] = archive.extractfile(member).read()
    licenses = []
    for name in entry['license_files']:
        if name not in members:
            raise ValueError(f'supplemental firmware license missing: {name}')
        license_name = f'{entry["name"]}-{PurePosixPath(name).name}'
        target = destination(metadata_dir, f'licenses/{license_name}')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(members[name])
        licenses.append({'name': license_name, 'source_path': name,
                         'sha256': hashlib.sha256(members[name]).hexdigest(), 'size': len(members[name])})
    if not licenses or not entry['license']:
        raise ValueError('supplemental firmware lacks licensing provenance')
    result = {}
    for name, path in entry['files'].items():
        safe_name(name)
        safe_name(path)
        if path not in members:
            raise ValueError(f'pinned supplemental firmware archive lacks declared blob: {path}')
        result[name] = {'data': members[path], 'source_path': path,
                        'source_repository': entry['url'], 'source_revision': expected,
                        'source_release': entry['release'], 'license': entry['license'],
                        'licenses': [record['name'] for record in licenses]}
        if entry.get('trusted_certificate'):
            result[name]['signer_certificate_sha256'] = entry['trusted_certificate']['sha256']
    return result, licenses


def _archive_compatible(entry, source, requirements, drivers=()):
    certificate = entry.get('trusted_certificate')
    if not certificate:
        return True
    # Unsigned DB users can use the newest data without a trusted signer. For
    # signed users, choose only a release whose signer is compiled into this
    # source tree. Never relax CFG80211_REQUIRE_SIGNED_REGDB to make it work.
    if not any(fnmatch.fnmatchcase(certificate['signature'], expression) for expression in requirements):
        return True
    source = Path(source).resolve()
    cfg80211 = next((driver for driver in drivers if driver['symbol'] == 'CFG80211'), {})
    if cfg80211.get('regdb_use_kernel_keys', True):
        path = source / safe_name(certificate['path'])
        if not path.resolve().is_relative_to(source):
            raise ValueError('regulatory certificate escapes kernel source')
        if path.is_file():
            text = _without_comments(path.read_text())
            der = bytes(int(value, 16) for value in re.findall(r'\b0x([0-9A-Fa-f]{2})\b', text))
            if der and hashlib.sha256(der).hexdigest() == certificate['sha256']:
                return True
    if cfg80211.get('regdb_extra_keydir'):
        directory = Path(cfg80211['regdb_extra_keydir'])
        if not directory.is_absolute():
            directory = source / directory
        for path in directory.glob('*.x509'):
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == certificate['sha256']:
                return True
    return False


def stage_firmware(source, drivers, staging, metadata_dir, firmware_lock=None, cache_dir=None, *, strict=False):
    """Stage enabled USB-driver blobs; return a complete/partial/none manifest.

    Missing source blobs and unresolved names are recorded, and only cause an
    error with strict=True. Network, integrity, unsafe path and license errors
    always raise. Callers use manifest['names'] for CONFIG_EXTRA_FIRMWARE.
    """
    if firmware_lock is None:
        firmware_lock = DEFAULT_LOCK
    lock = json.loads(Path(firmware_lock).read_text()) if not isinstance(firmware_lock, dict) else firmware_lock
    requirements = collect_firmware(source, drivers)
    staging, metadata_dir = Path(staging), Path(metadata_dir)
    staging.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    repository = FirmwareRepository(lock, cache_dir)
    manifest = {'source': {k: lock[k] for k in ('repository', 'revision', 'release') if k in lock},
                'files': [], 'names': [], 'missing': [], 'unresolved': requirements['unresolved'],
                'no_firmware_drivers': sorted(k for k, v in requirements['drivers'].items() if v['no_firmware']),
                'drivers': requirements['drivers'], 'licenses': [], 'status': 'none'}
    # A set of truly firmware-free drivers needs no network transfer.
    if not requirements['files']:
        manifest['status'] = 'partial' if manifest['unresolved'] else 'complete'
    else:
        declared_supplemental = {name for entry in lock.get('extra_sources', []) for name in entry['files']}
        records, links = {}, {}
        # Supplemental-only firmware (e.g. regdb) needs no unrelated repository
        # transfer. Mixed USB builds still retain the pinned full WHENCE file.
        if any(expression not in declared_supplemental for expression in requirements['files']):
            whence, _ = repository.read('WHENCE')
            if lock.get('whence_sha256') and hashlib.sha256(whence).hexdigest() != lock['whence_sha256']:
                raise ValueError('pinned linux-firmware WHENCE checksum mismatch')
            destination(metadata_dir, 'WHENCE').write_bytes(whence)
            records, links = parse_whence(whence.decode())
        supplemental, retained = {}, {}
        for entry in lock.get('extra_sources', []):
            if (not all(name in supplemental for name in entry['files']) and
                    any(fnmatch.fnmatchcase(name, expression) for name in entry['files'] for expression in requirements['files']) and
                    _archive_compatible(entry, source, requirements['files'], drivers)):
                blobs, licenses = _archive_source(entry, metadata_dir, cache_dir)
                supplemental.update(blobs)
                retained.update((record['name'], record) for record in licenses)
        wanted = {}
        for expression, symbols in sorted(requirements['files'].items()):
            matches = sorted(fnmatch.filter(set(records) | set(supplemental), expression)) if any(c in expression for c in '*?[') else [expression]
            if not matches:
                manifest['missing'].append({'name': expression, 'drivers': symbols, 'reason': 'no WHENCE paths match catalog pattern'})
            for name in matches:
                wanted.setdefault(name, set()).update(symbols)
        for name, symbols in sorted(wanted.items()):
            if name in supplemental:
                item = dict(supplemental[name])
                data = item.pop('data')
                if not data:
                    raise ValueError(f'empty supplemental firmware blob: {name}')
                output = destination(staging, name)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
                manifest['files'].append({'name': name, 'drivers': sorted(symbols),
                                          'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), **item})
                continue
            if name in declared_supplemental:
                manifest['missing'].append({'name': name, 'drivers': sorted(symbols),
                                            'reason': 'no pinned regulatory release matches a trusted kernel signer certificate'})
                continue
            try:
                data, original = _read_blob(repository, name, links)
            except FileNotFoundError:
                manifest['missing'].append({'name': name, 'drivers': sorted(symbols), 'reason': 'absent from pinned firmware source'})
                continue
            record = records.get(name) or records.get(original.removesuffix('.xz').removesuffix('.zst').removesuffix('.gz'))
            if not record:
                raise ValueError(f'firmware lacks WHENCE provenance: {name}')
            license_names = _license_files(repository, record, metadata_dir, retained)
            output = destination(staging, name)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            # Retain inline license terms with each requested name as well.
            provenance = destination(metadata_dir, f'whence/{name}.txt')
            provenance.parent.mkdir(parents=True, exist_ok=True)
            provenance.write_text(record['whence'])
            manifest['files'].append({'name': name, 'drivers': sorted(symbols), 'source_path': original,
                                      'source_repository': lock['repository'], 'source_revision': lock['revision'],
                                      'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
                                      'license': record['license'], 'licenses': license_names})
        manifest['names'] = [file['name'] for file in manifest['files']]
        manifest['licenses'] = [retained[name] for name in sorted(retained)]
        manifest['status'] = ('partial' if manifest['files'] else 'none') if (manifest['missing'] or manifest['unresolved']) else 'complete'
    destination(metadata_dir, 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    if strict and (manifest['missing'] or manifest['unresolved']):
        raise ValueError(f'USB WiFi firmware incomplete; see {metadata_dir / "manifest.json"}')
    return manifest
