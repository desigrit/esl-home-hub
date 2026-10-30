"""Package only application source, never credentials, reports, or sibling projects."""
from pathlib import Path
import io
import tarfile

root = Path(__file__).resolve().parents[1]
out = root / '.private' / 'ronhub-release.tar.gz'
out.parent.mkdir(exist_ok=True)
with tarfile.open(out, 'w:gz') as archive:
    for folder in ('ronhub', 'tools'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.name != 'remote_session.py':
                info = archive.gettarinfo(path, arcname=path.relative_to(root))
                info.mode = 0o644
                data = path.read_bytes()
                if path.suffix in ('.py', '.js', '.css', '.html', '.svg', '.json', '.txt', '.md', '.ps1'):
                    data = data.replace(b'\r\n', b'\n')
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
print(out)
