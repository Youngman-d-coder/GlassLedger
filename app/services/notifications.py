from datetime import date, datetime, timezone
from ..extensions import db
from ..models import Notification, Item, BackupRecord, AppSetting
from .intelligence import insight

def refresh_notifications():
    Notification.query.filter(Notification.dedupe_key.like('auto:%')).delete(synchronize_session=False)
    for item in Item.query.filter_by(is_active=True).all():
        x = insight(item)
        if x['balance'] <= 0:
            _add('danger', f'{item.name} is out of stock', 'No usable stock remains.', f'/inventory/{item.id}', f'auto:out:{item.id}')
        elif item.critical_stock_base and x['balance'] <= item.critical_stock_base:
            _add('danger', f'{item.name} is critical', 'Stock is at or below the configured critical level.', f'/inventory/{item.id}', f'auto:critical:{item.id}')
        elif item.minimum_stock_base and x['balance'] <= item.minimum_stock_base:
            _add('warning', f'{item.name} is low', 'Current balance is below the configured minimum.', f'/inventory/{item.id}', f'auto:low:{item.id}')
        if x['days_left'] is not None and x['days_left'] <= 14:
            _add('warning', f'{item.name} may run out soon', f'Estimated {x["days_left"]:.1f} days of stock remaining.', f'/inventory/{item.id}', f'auto:forecast:{item.id}')
        if x['expiry']:
            e = x['expiry'][0]
            suffix = ' Possible expiry waste at current consumption.' if e.get('waste_risk') else ''
            _add('warning', f'{item.name} has expiry risk', f'Batch {e["batch"]} expires in {e["days"]} day(s).{suffix}', f'/inventory/{item.id}', f'auto:expiry:{item.id}')
        if x['anomalies']:
            _add('info', f'Unusual movement: {item.name}', x['anomalies'][0], f'/inventory/{item.id}', f'auto:anom:{item.id}')

    latest = BackupRecord.query.order_by(BackupRecord.created_at.desc()).first()
    if not latest:
        _add('warning', 'No backup recorded yet', 'Create your first GlassLedger backup.', '/settings/', 'auto:backup:none')
    else:
        created = latest.created_at if latest.created_at.tzinfo else latest.created_at.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days
        if age_days >= 2:
            _add('danger', 'Backups are overdue', f'Last successful backup was {age_days} days ago.', '/settings/', 'auto:backup:overdue')
        if latest.status != 'HEALTHY':
            _add('danger', 'Latest backup failed integrity check', latest.filename, '/settings/', 'auto:backup:corrupt')

    hosting = AppSetting.query.filter_by(key='last_hosting_check').first()
    if not hosting or not hosting.value:
        _add('info', 'Hosting check recommended', 'Review Railway usage/free-plan status when convenient.', '/settings/', 'auto:hosting:first')
    else:
        try:
            days = (date.today() - date.fromisoformat(hosting.value)).days
            if days >= 30:
                _add('info', 'Monthly hosting check due', 'Review Railway resource usage and free-plan status.', '/settings/', 'auto:hosting:monthly')
        except ValueError:
            pass
    db.session.commit()

def _add(level, title, message, link, key):
    db.session.add(Notification(level=level, title=title, message=message, link=link, dedupe_key=key))
