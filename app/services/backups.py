import hashlib
import shutil
import sqlite3
from datetime import datetime, date
from pathlib import Path
from flask import current_app
from ..extensions import db
from ..models import BackupRecord


def backup_dir():
    path = Path(current_app.config['BACKUP_DIR'])
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path():
    uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    if not uri.startswith('sqlite:///'):
        raise RuntimeError('GlassLedger V1 backup service currently supports SQLite databases only.')
    return Path(uri.replace('sqlite:///', '', 1))


def integrity(path):
    try:
        conn = sqlite3.connect(str(path))
        result = conn.execute('PRAGMA integrity_check').fetchone()[0]
        conn.close()
        return result == 'ok'
    except Exception:
        return False


def _record(path, note, storage='LOCAL'):
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    rec = BackupRecord(
        filename=path.name, storage=storage, size_bytes=path.stat().st_size,
        sha256=sha, status='HEALTHY' if integrity(path) else 'CORRUPT', notes=note,
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def create_backup(note='Manual backup'):
    source_path = db_path()
    if not source_path.exists():
        raise RuntimeError('The SQLite database does not exist yet.')
    dst = backup_dir() / f'glassledger_{datetime.now():%Y-%m-%d_%H%M%S}.db'
    source = sqlite3.connect(str(source_path))
    target = sqlite3.connect(str(dst))
    source.backup(target)
    target.close()
    source.close()
    rec = _record(dst, note)
    rotate()
    return rec


def rotate(keep=12):
    files = sorted(backup_dir().glob('glassledger_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[keep:]:
        try:
            path.unlink()
            rec = BackupRecord.query.filter_by(filename=path.name).first()
            if rec and not rec.drive_file_id:
                db.session.delete(rec)
        except OSError:
            continue
    db.session.commit()


def import_backup(file_storage):
    original = Path(file_storage.filename or 'uploaded.db').name
    if not original.lower().endswith('.db'):
        raise ValueError('Backup file must be a .db SQLite file.')
    dst = backup_dir() / f'imported_{datetime.now():%Y-%m-%d_%H%M%S}.db'
    file_storage.save(dst)
    if not integrity(dst):
        dst.unlink(missing_ok=True)
        raise ValueError('The uploaded database failed SQLite integrity validation.')
    return _record(dst, f'Imported from {original}')


def _copy_into_live(src):
    # Release SQLAlchemy connections before replacing the SQLite file.
    db.session.remove()
    db.engine.dispose()
    shutil.copy2(src, db_path())
    if not integrity(db_path()):
        raise RuntimeError('Restore copy failed the post-restore integrity check.')


def restore_backup(filename):
    src = backup_dir() / Path(filename).name
    if not src.exists() or not integrity(src):
        raise ValueError('Backup does not exist locally or failed integrity validation.')
    create_backup('Emergency pre-restore backup')
    _copy_into_live(src)
    return True


def drive_upload(path):
    creds = current_app.config.get('GOOGLE_SERVICE_ACCOUNT_FILE')
    folder = current_app.config.get('GOOGLE_DRIVE_FOLDER_ID')
    if not creds or not folder:
        raise RuntimeError('Google Drive backup is not configured.')
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    credentials = service_account.Credentials.from_service_account_file(
        creds, scopes=['https://www.googleapis.com/auth/drive.file'])
    service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    metadata = {'name': Path(path).name, 'parents': [folder]}
    media = MediaFileUpload(str(path), mimetype='application/x-sqlite3', resumable=False)
    return service.files().create(body=metadata, media_body=media, fields='id').execute()['id']


def drive_download(file_id, filename):
    creds = current_app.config.get('GOOGLE_SERVICE_ACCOUNT_FILE')
    if not creds:
        raise RuntimeError('Google Drive backup is not configured.')
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import io
    credentials = service_account.Credentials.from_service_account_file(
        creds, scopes=['https://www.googleapis.com/auth/drive.file'])
    service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    path = backup_dir() / Path(filename).name
    path.write_bytes(buffer.getvalue())
    if not integrity(path):
        path.unlink(missing_ok=True)
        raise RuntimeError('Downloaded Google Drive backup failed integrity validation.')
    return path


def ensure_daily_backup():
    latest = BackupRecord.query.order_by(BackupRecord.created_at.desc()).first()
    if latest and latest.created_at.date() == date.today():
        return latest
    if not db_path().exists():
        return None
    rec = create_backup('Automatic daily backup')
    if current_app.config.get('AUTO_DRIVE_BACKUP') and current_app.config.get('GOOGLE_SERVICE_ACCOUNT_FILE') and current_app.config.get('GOOGLE_DRIVE_FOLDER_ID'):
        try:
            rec.drive_file_id = drive_upload(backup_dir() / rec.filename)
            rec.storage = 'LOCAL+DRIVE'
            db.session.commit()
        except Exception as exc:
            current_app.logger.exception('Automatic Google Drive backup failed: %s', exc)
    return rec
