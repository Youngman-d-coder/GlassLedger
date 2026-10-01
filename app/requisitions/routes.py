from datetime import date
from uuid import uuid4
from math import ceil
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Item, Requisition, RequisitionItem, Unit
from ..services.intelligence import insight
from ..services.inventory import packaging_for, decompose

bp = Blueprint('requisitions', __name__, url_prefix='/requisitions')

@bp.get('/')
@login_required
def index():
    return render_template('requisitions/index.html', requisitions=Requisition.query.order_by(Requisition.created_at.desc()).all(), page_title='Requisitions')

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    items = Item.query.filter_by(is_active=True).order_by(Item.name).all()
    suggestions = []
    for item in items:
        x = insight(item)
        if x['reorder_base'] > 0:
            unit_id = x['reorder_unit_id'] or item.base_unit_id
            unit = db.session.get(Unit, unit_id)
            suggestions.append((item, x, unit))
    if request.method == 'POST':
        req = Requisition(
            reference='REQ-' + date.today().strftime('%Y%m') + '-' + uuid4().hex[:5].upper(),
            period_month=date.today().month, period_year=date.today().year,
            status='FINALIZED', prepared_by_id=current_user.id,
            notes=request.form.get('notes'),
        )
        db.session.add(req); db.session.flush()
        for item, x, suggested_unit in suggestions:
            requested_qty = max(0, int(request.form.get(f'qty_{item.id}') or 0))
            requested_unit_id = int(request.form.get(f'unit_{item.id}') or suggested_unit.id)
            if requested_qty > 0:
                db.session.add(RequisitionItem(
                    requisition_id=req.id, item_id=item.id,
                    current_stock_base=x['balance'], average_usage_base=int(round(x['daily_usage'] * 30)),
                    target_stock_base=x['recommended_target'], suggested_quantity=x['reorder_qty'],
                    suggested_unit_id=suggested_unit.id, requested_quantity=requested_qty,
                    requested_unit_id=requested_unit_id, reason_or_note=request.form.get(f'note_{item.id}'),
                ))
        db.session.commit(); flash('Requisition created.', 'success')
        return redirect(url_for('requisitions.detail', req_id=req.id))
    return render_template('requisitions/new.html', suggestions=suggestions, page_title='Create Requisition')

@bp.get('/<int:req_id>')
@login_required
def detail(req_id):
    return render_template('requisitions/detail.html', req=Requisition.query.get_or_404(req_id), page_title='Requisition')
