from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import hashlib, secrets, json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, abort
from flask_login import login_required, current_user
from ..extensions import db
from ..models import StockTransaction, Item, Report, SharedReport, AppSetting
from ..services.inventory import decompose, current_balance
from ..services.intelligence import dashboard_intelligence

bp = Blueprint('reports', __name__, url_prefix='/reports')


def report_transactions(item_id=None, date_from=None, date_to=None, adjustments_only=False):
    q = StockTransaction.query
    if item_id:
        q = q.filter_by(item_id=item_id)
    if adjustments_only:
        q = q.filter(StockTransaction.transaction_type.in_(['ADJUSTMENT_IN', 'ADJUSTMENT_OUT']))
    if date_from:
        q = q.filter(StockTransaction.occurred_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        q = q.filter(StockTransaction.occurred_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    return q.order_by(StockTransaction.occurred_at.asc(), StockTransaction.id.asc()).all()


def _tx_row(t):
    return {
        'reference': t.reference,
        'date': t.occurred_at.isoformat(),
        'date_label': t.occurred_at.strftime('%d %b %Y %H:%M'),
        'item': t.item.name,
        'type': t.transaction_type,
        'type_label': t.transaction_type.replace('_', ' ').title(),
        'entered_quantity': t.entered_quantity,
        'unit': t.entered_unit.name,
        'base_quantity': t.base_quantity,
        'base_unit': t.item.base_unit.name,
        'before': t.balance_before,
        'after': t.balance_after,
        'destination': t.department_or_destination or '—',
        'purpose': t.purpose or '—',
        'notes': t.notes or '',
        'performed_by': t.performed_by.display_name if t.performed_by else '—',
        'batch': t.batch.batch_number if t.batch else None,
    }


def _snapshot(kind, txs, item, df, dt, notes):
    items = Item.query.filter_by(is_active=True).order_by(Item.name).all()
    settings = {s.key: s.value for s in AppSetting.query.all()}
    intel = dashboard_intelligence(items)
    rows = [_tx_row(t) for t in txs]
    per_item = []
    grouped = {}
    for t in txs:
        grouped.setdefault(t.item_id, []).append(t)
    selected_items = [item] if item else items
    for obj in selected_items:
        its = grouped.get(obj.id, [])
        if its:
            opening = its[0].balance_before
            closing = its[-1].balance_after
        else:
            # No movement in period: current balance is a useful stable summary.
            opening = closing = current_balance(obj.id)
        received = sum(t.base_quantity for t in its if t.transaction_type in {'RECEIPT', 'RETURN_IN', 'OPENING_BALANCE', 'ADJUSTMENT_IN'})
        issued = sum(t.base_quantity for t in its if t.transaction_type in {'ISSUE', 'RETURN_OUT', 'DAMAGED', 'EXPIRED', 'ADJUSTMENT_OUT'})
        adjustments = sum((t.base_quantity if t.transaction_type == 'ADJUSTMENT_IN' else -t.base_quantity) for t in its if t.transaction_type.startswith('ADJUSTMENT'))
        per_item.append({
            'name': obj.name, 'base_unit': obj.base_unit.name, 'opening': opening,
            'received': received, 'issued': issued, 'adjustments': adjustments, 'closing': closing,
        })
    attention = []
    for x in intel:
        if x['balance'] <= 0:
            attention.append({'level': 'Critical', 'item': x['item'].name, 'message': 'Out of stock'})
        elif x['item'].minimum_stock_base and x['balance'] <= x['item'].minimum_stock_base:
            attention.append({'level': 'Warning', 'item': x['item'].name, 'message': 'Below minimum stock'})
        if x['days_left'] is not None and x['days_left'] <= 14:
            attention.append({'level': 'Warning', 'item': x['item'].name, 'message': f'~{x["days_left"]:.1f} days of stock remaining'})
        if x['expiry']:
            e = x['expiry'][0]
            attention.append({'level': 'Expiry', 'item': x['item'].name, 'message': f'Batch {e["batch"]} expires in {e["days"]} day(s)'})
        for msg in x['anomalies']:
            attention.append({'level': 'Anomaly', 'item': x['item'].name, 'message': msg})
    return {
        'kind': kind,
        'period': {'from': df.isoformat(), 'to': dt.isoformat()},
        'notes': notes or '',
        'settings': settings,
        'transactions': rows,
        'item_summary': per_item,
        'attention': attention,
        'summary': {
            'transactions': len(rows),
            'receipts': sum(1 for t in txs if t.transaction_type in {'RECEIPT', 'RETURN_IN', 'OPENING_BALANCE'}),
            'issues': sum(1 for t in txs if t.transaction_type in {'ISSUE', 'RETURN_OUT'}),
            'adjustments': sum(1 for t in txs if t.transaction_type.startswith('ADJUSTMENT')),
            'attention': len(attention),
        },
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }


@bp.get('/')
@login_required
def index():
    return render_template('reports/index.html', reports=Report.query.order_by(Report.created_at.desc()).all(), items=Item.query.order_by(Item.name).all(), page_title='Reports')


@bp.post('/generate')
@login_required
def generate():
    kind = request.form.get('report_type', 'DAILY')
    allowed = {'DAILY', 'ITEM_TRACKING', 'STOCK_MOVEMENT', 'ADJUSTMENT', 'MONTHLY_SUMMARY'}
    if kind not in allowed:
        abort(400)
    item_id = request.form.get('item_id', type=int)
    df_raw, dt_raw = request.form.get('date_from'), request.form.get('date_to')
    if kind == 'MONTHLY_SUMMARY' and not df_raw:
        today = date.today(); df = today.replace(day=1); dt = today
    else:
        df = date.fromisoformat(df_raw) if df_raw else date.today()
        dt = date.fromisoformat(dt_raw) if dt_raw else date.today()
    if dt < df:
        flash('The report end date cannot be before the start date.', 'error')
        return redirect(url_for('reports.index'))
    item = Item.query.get(item_id) if item_id else None
    if kind == 'ITEM_TRACKING' and not item:
        flash('Choose an item for an Item Tracking report.', 'error')
        return redirect(url_for('reports.index'))
    txs = report_transactions(item_id, df, dt, adjustments_only=(kind == 'ADJUSTMENT'))
    ref = 'INV-' + kind[:5] + '-' + date.today().strftime('%Y%m%d') + '-' + uuid4().hex[:4].upper()
    title = kind.replace('_', ' ').title() + ' Report'
    snapshot = _snapshot(kind, txs, item, df, dt, request.form.get('notes'))
    report = Report(
        reference=ref, report_type=kind, title=title, date_from=df, date_to=dt,
        generated_by_id=current_user.id, item_id=item_id, notes=request.form.get('notes'),
        snapshot_json=snapshot, is_finalized=True,
    )
    db.session.add(report); db.session.commit()
    html = render_template('reports/print.html', report=report, snapshot=snapshot)
    outdir = Path(current_app.config['REPORT_DIR']); outdir.mkdir(parents=True, exist_ok=True)
    html_path = outdir / f'{ref}.html'; html_path.write_text(html, encoding='utf-8')
    report.html_path = str(html_path)
    report.file_hash = hashlib.sha256(html.encode()).hexdigest()
    try:
        from weasyprint import HTML
        pdf_path = outdir / f'{ref}.pdf'
        HTML(string=html, base_url=str(Path(current_app.root_path))).write_pdf(pdf_path)
        report.pdf_path = str(pdf_path)
        report.file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    except Exception as exc:
        current_app.logger.warning('PDF generation unavailable; HTML archive kept: %s', exc)
    db.session.commit()
    flash('Report finalized and archived.', 'success')
    return redirect(url_for('reports.view', report_id=report.id))


@bp.get('/<int:report_id>')
@login_required
def view(report_id):
    report = Report.query.get_or_404(report_id)
    return render_template('reports/view.html', report=report, snapshot=report.snapshot_json or {}, page_title=report.reference)


@bp.get('/<int:report_id>/download')
@login_required
def download(report_id):
    report = Report.query.get_or_404(report_id)
    path = Path(report.pdf_path) if report.pdf_path else (Path(report.html_path) if report.html_path else None)
    if not path or not path.exists():
        abort(404)
    return send_file(path, as_attachment=True)


@bp.post('/<int:report_id>/share')
@login_required
def share(report_id):
    report = Report.query.get_or_404(report_id)
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    hours = max(1, min(168, int(request.form.get('hours') or 24)))
    share = SharedReport(
        report_id=report.id, token_hash=token_hash, created_by_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
        allow_download=bool(request.form.get('allow_download')),
    )
    db.session.add(share); db.session.commit()
    return render_template('reports/share.html', report=report, share_url=url_for('reports.shared', token=raw, _external=True), page_title='Share Report')


def _valid_share(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    share = SharedReport.query.filter_by(token_hash=token_hash).first_or_404()
    now = datetime.now(timezone.utc)
    expires = share.expires_at if share.expires_at.tzinfo else share.expires_at.replace(tzinfo=timezone.utc)
    if share.revoked_at or expires < now:
        abort(410)
    return share


@bp.get('/shared/<token>')
def shared(token):
    share = _valid_share(token)
    share.access_count += 1; share.last_accessed_at = datetime.now(timezone.utc); db.session.commit()
    return render_template('reports/public.html', share=share, report=share.report, snapshot=share.report.snapshot_json or {}, token=token)


@bp.get('/shared/<token>/download')
def shared_download(token):
    share = _valid_share(token)
    if not share.allow_download:
        abort(403)
    report = share.report
    path = Path(report.pdf_path) if report.pdf_path else (Path(report.html_path) if report.html_path else None)
    if not path or not path.exists(): abort(404)
    share.access_count += 1; share.last_accessed_at = datetime.now(timezone.utc); db.session.commit()
    return send_file(path, as_attachment=True)


@bp.post('/share/<int:share_id>/revoke')
@login_required
def revoke_share(share_id):
    share = SharedReport.query.get_or_404(share_id)
    share.revoked_at = datetime.now(timezone.utc); db.session.commit()
    flash('Shared link revoked.', 'success')
    return redirect(url_for('reports.view', report_id=share.report_id))
