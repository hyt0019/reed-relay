"""Portable data directory selection and non-destructive migration."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from .core.score import atomic_json


def suggested_file(directory, title, suffix):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:120] or '曲谱'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{n}' for prefix in ('COM', 'LPT') for n in range(1, 10)}:
        name = '_'+name
    return str(Path(directory)/(name+suffix))


def application_root():
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).resolve().parent
        if root.name in {'ReedRelay-Player', 'ReedRelay-Converter'}:
            root = root.parent
        # Local builds share settings with the source launchers.
        if root.name == 'dist' and (root.parent/'src/reed_relay').is_dir():
            root = root.parent
        return root
    return Path(__file__).resolve().parents[2]


def legacy_directory():
    return Path(os.environ.get('APPDATA', str(Path.home())))/'ReedRelay'


def ensure_writable(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    fd, probe = tempfile.mkstemp(prefix='.reed-write-', dir=directory)
    os.close(fd)
    Path(probe).unlink()
    return directory


def rewrite_paths(value, source, target):
    if isinstance(value, dict):
        return {key: rewrite_paths(item, source, target) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_paths(item, source, target) for item in value]
    if isinstance(value, str):
        path = Path(value)
        if path.is_absolute():
            try:
                return str(target/path.relative_to(source))
            except ValueError:
                pass
    return value


def copy_data(source, target, snapshots=None):
    """Preflight conflicts, copy durable files, return newly created paths.

    Temporary audio is regenerated. Originals remain intact and rollback only
    removes files created by this call, never pre-existing target content.
    """
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        return []
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError('请选择独立的数据文件夹，不能选择当前目录的上级或子目录')
    snapshots = snapshots or {}
    pending = {}
    for path in source.rglob('*') if source.is_dir() else []:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            continue
        if path.suffix.lower() in {'.tmp', '.part', '.log'} or path.name.startswith(('harmonica_', 'audition_', '.reed-write-')):
            continue
        relative = path.relative_to(source)
        content = path.read_bytes()
        if path.suffix.lower() == '.json':
            try:
                value = json.loads(content.decode('utf-8-sig'))
                content = json.dumps(rewrite_paths(value, source, target), ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
            except (UnicodeError, ValueError):
                pass
        pending[relative] = content
    for name, value in snapshots.items():
        pending[Path(name)] = json.dumps(rewrite_paths(value, source, target), ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    for relative, content in pending.items():
        destination = target/relative
        if not destination.resolve().is_relative_to(target):
            raise ValueError('数据目标路径无效')
        if destination.exists() and (not destination.is_file() or destination.read_bytes() != content):
            raise ValueError(f'目标目录已有不同的 {relative}，请选择空目录以保留双方数据')
    ensure_writable(target)
    created = []
    try:
        for relative, content in pending.items():
            destination = target/relative
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents overwriting a concurrent writer.
            with destination.open('xb') as stream:
                created.append(destination)
                stream.write(content)
        return created
    except Exception:
        rollback(created, target)
        raise


def rollback(paths, target):
    target = Path(target).resolve()
    for path in reversed(paths):
        if path.resolve().is_relative_to(target):
            path.unlink(missing_ok=True)


@dataclass
class Storage:
    root: Path | None = None
    legacy: Path | None = None
    initial_directory: Path | None = None

    def __post_init__(self):
        self.root = Path(self.root or application_root()).resolve()
        self.locator = self.root/'storage-location.json'
        self.legacy = Path(self.legacy or legacy_directory()).resolve()
        self.notice = ''
        self.fixed = bool(os.environ.get('REED_RELAY_DATA_DIR'))
        if self.fixed:
            self.directory = ensure_writable(os.environ['REED_RELAY_DATA_DIR'])
            return
        if self.locator.exists():
            raw = json.loads(self.locator.read_text(encoding='utf-8-sig'))
            self.directory = ensure_writable(raw['directory'])
            return
        self.directory = ensure_writable(self.initial_directory or self.root/'local-data')
        created = []
        try:
            if self.legacy != self.directory and self.legacy.is_dir():
                created = copy_data(self.legacy, self.directory)
                self.notice = f'旧数据已复制到 {self.directory}，原目录保留'
            atomic_json(self.locator, {'directory':str(self.directory)})
        except Exception as error:
            rollback(created, self.directory)
            if self.initial_directory is not None:
                # A first-launch choice must never fall back to the C drive
                # when recording that choice fails.
                raise
            self.notice = f'使用程序旁的数据目录；旧数据迁移或位置记录失败：{error}'

    def choose(self, target, snapshots=None):
        if self.fixed:
            raise ValueError('启动配置 REED_RELAY_DATA_DIR 已固定目录，请移除该配置后再选择目录')
        target = Path(target).expanduser().resolve()
        if target == self.directory:
            return target
        created = copy_data(self.directory, target, snapshots)
        try:
            atomic_json(self.locator, {'directory':str(target)})
        except Exception:
            rollback(created, target)
            raise
        self.directory = target
        return target
