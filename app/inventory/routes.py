from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Item, Category, Unit, ItemPackaging, ItemAlias, StockTransaction, StockBatch
from ..services.text import normalize_name, slugify, normalize_note
from ..services.inventory import current_balance, decompose, packaging_for
from ..services.intelligence import insight
from ..services.audit import audit

bp = Blueprint('inventory', __name__, url_prefix='/inventory')

def _active_units():
    return Unit.query.filter_by(is_active=True).order_by(Unit.name).all()

def _preferred_or_none(raw):
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None

@bp.get('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    query = Item.query.filter_by(is_active=True)
    if q:
        like = f'%{q}%'
        query = query.filter(Item.name.ilike(like))
    items = query.order_by(Item.name).all()
    rows = []
    for item in items:
        bal = current_balance(item.id)
        rows.append((item, bal, decompose(item, bal), insight(item)))
    return render_template('inventory/index.html', rows=rows, q=q, page_title='Inventory')

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    units = _active_units()
    if not categories or not units:
        flash('Add at least one category and one unit first.', 'error')
        return redirect(url_for('settings.index'))
    if request.method == 'POST':
        name = normalize_name(request.form['name'])
        if Item.query.filter(db.func.lower(Item.name) == name.lower()).first():
            flash('That product already exists.', 'error')
            return redirect(url_for('inventory.new'))
        base_unit_id = int(request.form['base_unit_id'])
        item = Item(
            name=name,
            slug=slugify(name),
            sku=(request.form.get('sku') or '').strip() or None,
            description=normalize_note(request.form.get('description')),
            category_id=int(request.form['category_id']),
            base_unit_id=base_unit_id,
            minimum_stock_base=max(0, int(request.form.get('minimum_stock_base') or 0)),
            critical_stock_base=max(0, int(request.form.get('critical_stock_base') or 0)),
            target_stock_base=max(0, int(request.form.get('target_stock_base') or 0)),
            expiry_warning_days=max(0, int(request.form.get('expiry_warning_days') or 30)),
            expiry_tracking=bool(request.form.get('expiry_tracking')),
            batch_tracking=bool(request.form.get('batch_tracking')),
            preferred_receive_unit_id=_preferred_or_none(request.form.get('preferred_receive_unit_id')) or base_unit_id,
            preferred_issue_unit_id=_preferred_or_none(request.form.get('preferred_issue_unit_id')) or base_unit_id,
            preferred_display_unit_id=_preferred_or_none(request.form.get('preferred_display_unit_id')) or base_unit_id,
            preferred_requisition_unit_id=_preferred_or_none(request.form.get('preferred_requisition_unit_id')) or base_unit_id,
        )
        db.session.add(item)
        db.session.flush()
        db.session.add(ItemPackaging(item_id=item.id, unit_id=base_unit_id, base_quantity=1, sort_order=0, is_active=True))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('A product with that name, SKU, or slug already exists.', 'error')
            return redirect(url_for('inventory.new'))
        audit(current_user, 'CREATE', 'Item', item.id, f'Created {item.name}')
        flash('Product created. Configure packaging and opening stock next.', 'success')
        return redirect(url_for('inventory.detail', item_id=item.id))
    return render_template('inventory/form.html', item=None, categories=categories, units=units, page_title='Add Product')

@bp.route('/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(item_id):
    item = Item.query.get_or_404(item_id)
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    units = _active_units()
    if request.method == 'POST':
        before = {
            'name': item.name,
            'minimum_stock_base': item.minimum_stock_base,
            'critical_stock_base': item.critical_stock_base,
            'target_stock_base': item.target_stock_base,
        }
        item.name = normalize_name(request.form['name'])
        item.slug = slugify(item.name)
        item.sku = (request.form.get('sku') or '').strip() or None
        item.description = normalize_note(request.form.get('description'))
        item.category_id = int(request.form['category_id'])
        item.minimum_stock_base = max(0, int(request.form.get('minimum_stock_base') or 0))
        item.critical_stock_base = max(0, int(request.form.get('critical_stock_base') or 0))
        item.target_stock_base = max(0, int(request.form.get('target_stock_base') or 0))
        item.expiry_warning_days = max(0, int(request.form.get('expiry_warning_days') or 30))
        item.expiry_tracking = bool(request.form.get('expiry_tracking'))
        item.batch_tracking = bool(request.form.get('batch_tracking'))
        item.preferred_receive_unit_id = _preferred_or_none(request.form.get('preferred_receive_unit_id'))
        item.preferred_issue_unit_id = _preferred_or_none(request.form.get('preferred_issue_unit_id'))
        item.preferred_display_unit_id = _preferred_or_none(request.form.get('preferred_display_unit_id'))
        item.preferred_requisition_unit_id = _preferred_or_none(request.form.get('preferred_requisition_unit_id'))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('That name or SKU is already in use.', 'error')
            return redirect(url_for('inventory.edit', item_id=item.id))
        audit(current_user, 'UPDATE', 'Item', item.id, f'Edited {item.name}', before=before, after={
            'name': item.name,
            'minimum_stock_base': item.minimum_stock_base,
            'critical_stock_base': item.critical_stock_base,
            'target_stock_base': item.target_stock_base,
        })
        flash('Product updated.', 'success')
        return redirect(url_for('inventory.detail', item_id=item.id))
    return render_template('inventory/form.html', item=item, categories=categories, units=units, page_title='Edit Product')

@bp.get('/<int:item_id>')
@login_required
def detail(item_id):
    item = Item.query.get_or_404(item_id)
    bal = current_balance(item.id)
    txs = StockTransaction.query.filter_by(item_id=item.id).order_by(StockTransaction.occurred_at.desc()).limit(100).all()
    batches = StockBatch.query.filter_by(item_id=item.id).order_by(StockBatch.expiry_date.asc().nullslast(), StockBatch.id.asc()).all()
    return render_template(
        'inventory/detail.html', item=item, balance=bal, balance_label=decompose(item, bal),
        insight=insight(item), transactions=txs, units=_active_units(), batches=batches,
        page_title=item.name,
    )

@bp.post('/<int:item_id>/packaging')
@login_required
def packaging(item_id):
    item = Item.query.get_or_404(item_id)
    unit_id = int(request.form['unit_id'])
    if unit_id == item.base_unit_id:
        flash('The base unit is always equal to 1 and cannot be redefined.', 'error')
        return redirect(url_for('inventory.detail', item_id=item.id))
    inner_id = request.form.get('inner_packaging_id', type=int)
    contains_qty = request.form.get('contains_quantity', type=int)
    direct_base = request.form.get('base_quantity', type=int)
    if inner_id and contains_qty:
        inner = ItemPackaging.query.filter_by(item_id=item.id, id=inner_id, is_active=True).first()
        if not inner:
            flash('The selected inner packaging level is invalid.', 'error')
            return redirect(url_for('inventory.detail', item_id=item.id))
        base = contains_qty * inner.base_quantity
        parent_id = inner.id
    elif direct_base:
        base = direct_base
        parent_id = None
        contains_qty = None
    else:
        flash('Enter either a direct base conversion or a contains quantity and inner unit.', 'error')
        return redirect(url_for('inventory.detail', item_id=item.id))
    if base <= 1:
        flash('Packaging must contain more than one base unit.', 'error')
        return redirect(url_for('inventory.detail', item_id=item.id))
    existing = ItemPackaging.query.filter_by(item_id=item.id, unit_id=unit_id).first()
    if existing:
        existing.base_quantity = base
        existing.parent_packaging_id = parent_id
        existing.quantity_in_parent = contains_qty
        existing.sort_order = base
        existing.is_active = True
    else:
        db.session.add(ItemPackaging(
            item_id=item.id, unit_id=unit_id, parent_packaging_id=parent_id,
            quantity_in_parent=contains_qty, base_quantity=base, sort_order=base, is_active=True,
        ))
    db.session.commit()
    audit(current_user, 'PACKAGING', 'Item', item.id, f'Updated packaging for {item.name}')
    flash('Packaging conversion saved. Historical transactions keep their original conversion.', 'success')
    return redirect(url_for('inventory.detail', item_id=item.id))

@bp.post('/<int:item_id>/packaging/<int:packaging_id>/toggle')
@login_required
def toggle_packaging(item_id, packaging_id):
    item = Item.query.get_or_404(item_id)
    p = ItemPackaging.query.filter_by(id=packaging_id, item_id=item.id).first_or_404()
    if p.unit_id == item.base_unit_id:
        flash('The base unit cannot be disabled.', 'error')
    else:
        p.is_active = not p.is_active
        db.session.commit()
        audit(current_user, 'PACKAGING_TOGGLE', 'Item', item.id, f'{"Enabled" if p.is_active else "Disabled"} {p.unit.name}')
        flash('Packaging status updated.', 'success')
    return redirect(url_for('inventory.detail', item_id=item.id))

@bp.post('/<int:item_id>/alias')
@login_required
def add_alias(item_id):
    item = Item.query.get_or_404(item_id)
    alias = normalize_name(request.form.get('alias', ''))
    key = alias.lower()
    if not alias:
        flash('Alias cannot be empty.', 'error')
    elif ItemAlias.query.filter_by(normalized_alias=key).first():
        flash('That alias is already in use.', 'error')
    else:
        db.session.add(ItemAlias(item_id=item.id, alias=alias, normalized_alias=key))
        db.session.commit()
        audit(current_user, 'ALIAS', 'Item', item.id, f'Added alias {alias}')
        flash('Alias added.', 'success')
    return redirect(url_for('inventory.detail', item_id=item.id))

@bp.post('/<int:item_id>/toggle')
@login_required
def toggle(item_id):
    item = Item.query.get_or_404(item_id)
    item.is_active = not item.is_active
    db.session.commit()
    audit(current_user, 'TOGGLE', 'Item', item.id, f'{"Activated" if item.is_active else "Deactivated"} {item.name}')
    flash('Product status updated.', 'success')
    return redirect(url_for('inventory.detail', item_id=item.id))

@bp.get('/<int:item_id>/unit-data')
@login_required
def unit_data(item_id):
    item = Item.query.get_or_404(item_id)
    units = []
    for p in sorted((p for p in item.packaging_levels if p.is_active), key=lambda p: p.base_quantity):
        units.append({'id': p.unit_id, 'name': p.unit.name, 'factor': p.base_quantity})
    batches = []
    for b in StockBatch.query.filter_by(item_id=item.id, is_active=True).filter(StockBatch.remaining_base_quantity > 0).order_by(StockBatch.expiry_date.asc().nullslast(), StockBatch.id.asc()).all():
        batches.append({
            'id': b.id,
            'label': f'{b.batch_number or "Unlabelled"} — {b.remaining_base_quantity} base units' + (f' — exp {b.expiry_date.isoformat()}' if b.expiry_date else ''),
            'remaining': b.remaining_base_quantity,
            'expiry': b.expiry_date.isoformat() if b.expiry_date else None,
        })
    return jsonify({
        'item_id': item.id,
        'balance': current_balance(item.id),
        'balance_label': decompose(item, current_balance(item.id)),
        'base_unit': item.base_unit.name,
        'batch_tracking': bool(item.batch_tracking or item.expiry_tracking),
        'units': units,
        'batches': batches,
        'preferred_receive_unit_id': item.preferred_receive_unit_id,
        'preferred_issue_unit_id': item.preferred_issue_unit_id,
    })
