from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Item, StockBatch, StockAdjustment
from ..services.inventory import record_movement, current_balance, packaging_for

bp = Blueprint('transactions', __name__, url_prefix='/transactions')

@bp.route('/new/<kind>', methods=['GET', 'POST'])
@login_required
def new(kind):
    mapping = {
        'receive': 'RECEIPT', 'issue': 'ISSUE', 'adjust-in': 'ADJUSTMENT_IN',
        'adjust-out': 'ADJUSTMENT_OUT', 'opening': 'OPENING_BALANCE',
        'damaged': 'DAMAGED', 'expired': 'EXPIRED', 'return-in': 'RETURN_IN', 'return-out': 'RETURN_OUT',
    }
    tx_type = mapping.get(kind)
    if not tx_type:
        return 'Unknown transaction', 404
    items = Item.query.filter_by(is_active=True).order_by(Item.name).all()
    selected_id = request.args.get('item_id', type=int)
    selected = Item.query.get(selected_id) if selected_id else (items[0] if items else None)
    if not items:
        flash('Add a product before recording stock.', 'error')
        return redirect(url_for('inventory.new'))

    if request.method == 'POST':
        item = Item.query.get_or_404(int(request.form['item_id']))
        batch = None
        try:
            if tx_type in {'RECEIPT', 'OPENING_BALANCE', 'RETURN_IN'} and (item.batch_tracking or item.expiry_tracking):
                batch_number = (request.form.get('batch_number') or '').strip() or None
                expiry_raw = request.form.get('expiry_date') or None
                expiry_date = datetime.strptime(expiry_raw, '%Y-%m-%d').date() if expiry_raw else None
                if batch_number:
                    batch = StockBatch.query.filter_by(item_id=item.id, batch_number=batch_number).first()
                if not batch:
                    batch = StockBatch(
                        item=item, batch_number=batch_number, expiry_date=expiry_date,
                        initial_base_quantity=0, remaining_base_quantity=0,
                        supplier=(request.form.get('supplier') or '').strip() or None,
                    )
                    db.session.add(batch)
                    db.session.flush()
                else:
                    if expiry_date:
                        batch.expiry_date = expiry_date
                    if request.form.get('supplier'):
                        batch.supplier = request.form.get('supplier').strip()
            elif (item.batch_tracking or item.expiry_tracking) and tx_type in {'ISSUE', 'DAMAGED', 'EXPIRED', 'RETURN_OUT'}:
                batch_id = request.form.get('batch_id', type=int)
                if batch_id:
                    batch = StockBatch.query.filter_by(id=batch_id, item_id=item.id).first()

            tx = record_movement(
                item, tx_type, request.form['quantity'], request.form['unit_id'], current_user,
                request.form.get('destination'), request.form.get('purpose'), request.form.get('notes'), batch=batch,
            )
            if batch and tx_type in {'RECEIPT', 'OPENING_BALANCE', 'RETURN_IN'}:
                batch.initial_base_quantity += tx.base_quantity
                batch.is_active = True
                db.session.commit()
            if tx_type.startswith('ADJUSTMENT'):
                db.session.add(StockAdjustment(
                    transaction_id=tx.id, reason_code=request.form.get('reason_code') or 'Other',
                    reason_text=request.form.get('notes'), system_quantity=tx.balance_before,
                    physical_quantity=tx.balance_after, difference=tx.balance_after - tx.balance_before,
                    created_by_id=current_user.id,
                ))
                db.session.commit()
            flash('Transaction recorded successfully.', 'success')
            return redirect(url_for('inventory.detail', item_id=item.id))
        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(str(e), 'error')

    return render_template(
        'transactions/form.html', kind=kind, tx_type=tx_type, items=items, selected=selected,
        page_title=kind.replace('-', ' ').title() + ' Stock',
    )

@bp.route('/count/<int:item_id>', methods=['GET', 'POST'])
@login_required
def count(item_id):
    item = Item.query.get_or_404(item_id)
    before = current_balance(item.id)
    if request.method == 'POST':
        try:
            unit_id = int(request.form['unit_id'])
            qty = int(request.form['quantity'])
            if qty < 0:
                raise ValueError('Physical quantity cannot be negative.')
            physical = qty * packaging_for(item, unit_id)
            diff = physical - before
            if diff == 0:
                flash('Physical count matches GlassLedger. No adjustment needed.', 'success')
                return redirect(url_for('inventory.detail', item_id=item.id))
            tx_type = 'ADJUSTMENT_IN' if diff > 0 else 'ADJUSTMENT_OUT'
            factor = packaging_for(item, unit_id)
            if abs(diff) % factor == 0:
                entered, entered_unit = abs(diff) // factor, unit_id
            else:
                entered, entered_unit = abs(diff), item.base_unit_id
            tx = record_movement(
                item, tx_type, entered, entered_unit, current_user,
                purpose='Physical stock count', notes=request.form.get('notes'),
            )
            db.session.add(StockAdjustment(
                transaction_id=tx.id, reason_code='Physical Count Difference',
                reason_text=request.form.get('notes'), system_quantity=before,
                physical_quantity=physical, difference=diff, created_by_id=current_user.id,
            ))
            db.session.commit()
            flash('Physical count reconciled and recorded.', 'success')
            return redirect(url_for('inventory.detail', item_id=item.id))
        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(str(e), 'error')
    return render_template('transactions/count.html', item=item, balance=before, page_title='Physical Count')
