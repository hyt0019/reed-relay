"""A local score folder with validated, non-overwriting imports."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from .core.score import Score
from .storage import application_root


def supported_score(path):
    return Path(path).suffix.lower() in {'.mid', '.midi', '.json'}


def read_score(path):
    path = Path(path)
    if not supported_score(path):
        raise ValueError('请导入 MIDI（.mid/.midi）或 ReedRelay JSON 曲谱')
    score = Score.from_midi(path) if path.suffix.lower() in {'.mid', '.midi'} else Score.load(path)
    if not score.notes:
        raise ValueError('曲谱没有可用音符')
    return score


def default_library(data_dir):
    if os.environ.get('REED_RELAY_DATA_DIR'):
        return (Path(data_dir)/'演奏库').resolve()
    root = application_root()
    for path in (root/'样例文件'/'示例曲谱', root/'示例曲谱'):
        if path.is_dir(): return path.resolve()
    return (Path(data_dir)/'演奏库').resolve()


@dataclass(frozen=True)
class ImportedScore:
    path: Path
    created: bool


class ScoreLibrary:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self._cache = {}

    def scan(self):
        """Keep malformed files visible without blocking other songs."""
        if not self.directory.exists(): return []
        if not self.directory.is_dir(): raise ValueError('曲库路径不是文件夹')
        entries, current = [], {}
        for path in sorted(self.directory.rglob('*'), key=lambda p: str(p).casefold()):
            if not path.is_file() or path.is_symlink() or not supported_score(path): continue
            path = path.resolve()
            if not path.is_relative_to(self.directory): continue
            entry = {'path':str(path), 'filename':str(path.relative_to(self.directory)),
                     'title':path.stem.removesuffix('.reedscore'), 'format':'MIDI' if path.suffix.lower() != '.json' else 'JSON',
                     'duration':0., 'note_count':0, 'voice_count':0, 'minimum_pitch':0, 'maximum_pitch':0, 'error':''}
            try:
                stat = path.stat()
                key = (str(path), stat.st_mtime_ns, stat.st_size)
                if key in self._cache:
                    entry = dict(self._cache[key])
                else:
                    score = read_score(path)
                    entry.update(title=score.title, duration=score.duration_ms, note_count=len(score.notes),
                                 voice_count=len({n.voice for n in score.notes}),
                                 minimum_pitch=min(n.midi_pitch for n in score.notes),
                                 maximum_pitch=max(n.midi_pitch for n in score.notes))
                current[key] = dict(entry)
            except Exception as error:
                entry['error'] = str(error)
            entries.append(entry)
        self._cache = current
        return sorted(entries, key=lambda entry: (entry['title'].casefold(), entry['path'].casefold()))

    def import_score(self, source):
        source = Path(source).resolve()
        read_score(source)
        content = source.read_bytes()
        digest = hashlib.sha256(content).digest()
        self.directory.mkdir(parents=True, exist_ok=True)
        # Same content can have a different filename or extension case.
        for entry in self.scan():
            target = Path(entry['path'])
            if entry['error']: continue
            if target.stat().st_size == len(content) and hashlib.sha256(target.read_bytes()).digest() == digest:
                return ImportedScore(target, False)
        if source.name.lower().endswith('.reedscore.json'):
            stem, suffix = source.name[:-len('.reedscore.json')], '.reedscore.json'
        else:
            stem, suffix = source.stem, source.suffix
        for index in range(10000):
            target = self.directory/(source.name if index == 0 else f'{stem} ({index+1}){suffix}')
            try:
                stream = target.open('xb')
            except FileExistsError:
                continue
            try:
                with stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                read_score(target)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return ImportedScore(target, True)
        raise ValueError('同名曲谱过多，请重命名后再导入')
