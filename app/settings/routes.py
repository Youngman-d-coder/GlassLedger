from datetime import date
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Category, Unit, AppSetting, BackupRecord, AuditLog
from ..services.text import normalize_name, slugify
from ..services.backups import create_backup, restore_backup, backup_dir, drive_upload, drive_download, import_backup, integrity, db_path
from ..services.audit import audit

bp = Blueprint('settings', __name__, url_prefix='/settings')

def owner_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != 'OWNER':
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def _set(key, value):
    setting = AppSetting.query.filter_by(key=key).first() or AppSetting(key=key)
    setting.value = str(value)
    db.session.add(setting)

@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        for key in ['organization_name', 'department_name', 'report_footer', 'safety_buffer_pct', 'forecast_horizon_days']:
            _set(key, request.form.get(key, '').strip())
        db.session.commit()
        flash('Settings saved.', 'success')
    settings = {s.key: s.value for s in AppSetting.query.all()}
    db_file = db_path()
    health = {
        'database_ok': integrity(db_file) if db_file.exists() else False,
        'database_size': db_file.stat().st_size if db_file.exists() else 0,
        'drive_configured': bool(current_app.config.get('GOOGLE_SERVICE_ACCOUNT_FILE') and current_app.config.get('GOOGLE_DRIVE_FOLDER_ID')),
        'last_backup': BackupRecord.query.order_by(BackupRecord.created_at.desc()).first(),
        'hosting_checked': settings.get('last_hosting_check'),
    }
    return render_template(
        'settings/index.html', settings=settings,
        categories=Category.query.order_by(Category.name).all(),
        units=Unit.query.order_by(Unit.name).all(),
        backups=BackupRecord.query.order_by(BackupRecord.created_at.desc()).limit(30).all(),
        health=health, page_title='Settings',
    )

@bp.post('/category')
@owner_required
def category():
    name = normalize_name(request.form['name'])
    try:
        db.session.add(Category(name=name, slug=slugify(name), description=request.form.get('description')))
        db.session.commit()
        flash('Category added.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('That category already exists.', 'error')
    return redirect(url_for('settings.index'))

@bp.post('/category/<int:category_id>/edit')
@owner_required
def edit_category(category_id):
    row = Category.query.get_or_404(category_id)
    row.name = normalize_name(request.form['name']); row.slug = slugify(row.name)
    row.description = request.form.get('description')
    try: db.session.commit(); flash('Category updated.', 'success')
    except IntegrityError: db.session.rollback(); flash('That category name is already in use.', 'error')
    return redirect(url_for('settings.index'))

@bp.post('/category/<int:category_id>/toggle')
@owner_required
def toggle_category(category_id):
    row = Category.query.get_or_404(category_id); row.is_active = not row.is_active; db.session.commit(); flash('Category status updated.', 'success'); return redirect(url_for('settings.index'))

@bp.post('/unit')
@owner_required
def unit():
    name = normalize_name(request.form['name'])
    try:
        db.session.add(Unit(name=name, symbol=(request.form.get('symbol') or '').strip() or None, unit_type=request.form.get('unit_type', 'COUNT')))
        db.session.commit(); flash('Unit added.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('That unit already exists.', 'error')
    return redirect(url_for('settings.index'))

@bp.post('/unit/<int:unit_id>/edit')
@owner_required
def edit_unit(unit_id):
    row = Unit.query.get_or_404(unit_id); row.name = normalize_name(request.form['name']); row.symbol = (request.form.get('symbol') or '').strip() or None; row.unit_type = request.form.get('unit_type', row.unit_type)
    try: db.session.commit(); flash('Unit updated.', 'success')
    except IntegrityError: db.session.rollback(); flash('That unit name is already in use.', 'error')
    return redirect(url_for('settings.index'))

@bp.post('/unit/<int:unit_id>/toggle')
@owner_required
def toggle_unit(unit_id):
    row = Unit.query.get_or_404(unit_id); row.is_active = not row.is_active; db.session.commit(); flash('Unit status updated.', 'success'); return redirect(url_for('settings.index'))

@bp.post('/backup')
@owner_required
def backup():
    rec = create_backup(); flash(f'Backup {rec.filename} created.', 'success'); return redirect(url_for('settings.index'))

@bp.post('/backup/import')
@owner_required
def import_backup_route():
    upload = request.files.get('backup_file')
    if not upload: flash('Choose a backup file.', 'error')
    else:
        try: rec = import_backup(upload); flash(f'{rec.filename} imported and validated.', 'success')
        except Exception as exc: flash(str(exc), 'error')
    return redirect(url_for('settings.index'))

@bp.post('/backup/<int:backup_id>/drive')
@owner_required
def backup_drive(backup_id):
    rec = BackupRecord.query.get_or_404(backup_id)
    try:
        local = backup_dir() / rec.filename
        if not local.exists() and rec.drive_file_id: local = drive_download(rec.drive_file_id, rec.filename)
        rec.drive_file_id = drive_upload(local); rec.storage = 'LOCAL+DRIVE'; db.session.commit(); flash('Backup copied to Google Drive.', 'success')
    except Exception as exc: flash(f'Google Drive backup failed: {exc}', 'error')
    return redirect(url_for('settings.index'))

@bp.post('/backup/<int:backup_id>/restore')
@owner_required
def restore(backup_id):
    rec = BackupRecord.query.get_or_404(backup_id)
    try:
        local = backup_dir() / rec.filename
        if not local.exists() and rec.drive_file_id: drive_download(rec.drive_file_id, rec.filename)
        restore_backup(rec.filename)
        audit(current_user, 'RESTORE', 'Backup', rec.id, f'Restored {rec.filename}')
        flash('Backup restored and validated. Refresh the app before continuing.', 'success')
    except Exception as exc: flash(str(exc), 'error')
    return redirect(url_for('settings.index'))

@bp.get('/backup/<int:backup_id>/download')
@owner_required
def download_backup(backup_id):
    rec = BackupRecord.query.get_or_404(backup_id)
    local = backup_dir() / rec.filename
    if not local.exists() and rec.drive_file_id:
        drive_download(rec.drive_file_id, rec.filename)
    return send_from_directory(backup_dir(), rec.filename, as_attachment=True)

@bp.post('/hosting-checked')
@owner_required
def hosting_checked():
    _set('last_hosting_check', date.today().isoformat()); db.session.commit(); flash('Hosting check recorded.', 'success'); return redirect(url_for('settings.index'))

@bp.get('/audit')
@owner_required
def audit_log():
    return render_template('settings/audit.html', logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all(), page_title='Audit Trail')
