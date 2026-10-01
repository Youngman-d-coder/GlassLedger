from datetime import datetime, timezone
from uuid import uuid4
from ..extensions import db
from ..models import StockTransaction, ItemPackaging, AuditLog, StockBatch

IN_TYPES = {'RECEIPT', 'RETURN_IN', 'ADJUSTMENT_IN', 'OPENING_BALANCE'}
OUT_TYPES = {'ISSUE', 'RETURN_OUT', 'ADJUSTMENT_OUT', 'EXPIRED', 'DAMAGED'}

def current_balance(item_id):
    last = StockTransaction.query.filter_by(item_id=item_id).order_by(StockTransaction.id.desc()).first()
    return last.balance_after if last else 0

def packaging_for(item, unit_id):
    unit_id = int(unit_id)
    if unit_id == item.base_unit_id:
        return 1
    p = ItemPackaging.query.filter_by(item_id=item.id, unit_id=unit_id, is_active=True).first()
    if not p:
        raise ValueError('That unit is not configured for this product.')
    return p.base_quantity

def configured_units(item):
    return sorted((p for p in item.packaging_levels if p.is_active), key=lambda p: p.base_quantity)

def record_movement(item, tx_type, quantity, unit_id, user, department=None, purpose=None, notes=None, batch=None, occurred_at=None):
    quantity = int(quantity)
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    base = quantity * packaging_for(item, int(unit_id))
    before = current_balance(item.id)
    if tx_type in IN_TYPES:
        after = before + base
    elif tx_type in OUT_TYPES:
        if base > before:
            raise ValueError('Insufficient stock for this transaction.')
        after = before - base
    else:
        raise ValueError('Unsupported transaction type.')

    if (item.batch_tracking or item.expiry_tracking) and tx_type in {'ISSUE', 'DAMAGED', 'EXPIRED', 'RETURN_OUT'}:
        if not batch:
            raise ValueError('Select a batch for this batch-tracked product.')
        if batch.item_id != item.id:
            raise ValueError('The selected batch does not belong to this product.')
        if base > batch.remaining_base_quantity:
            raise ValueError('The selected batch does not contain enough stock. Issue from another batch separately.')

    tx = StockTransaction(
        reference='TX-' + datetime.now().strftime('%Y%m%d') + '-' + uuid4().hex[:8].upper(),
        item=item,
        batch=batch,
        transaction_type=tx_type,
        entered_quantity=quantity,
        entered_unit_id=int(unit_id),
        base_quantity=base,
        balance_before=before,
        balance_after=after,
        department_or_destination=department,
        purpose=purpose,
        notes=notes,
        performed_by=user,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.session.add(tx)
    if batch:
        if tx_type in IN_TYPES:
            batch.remaining_base_quantity += base
        elif tx_type in OUT_TYPES:
            batch.remaining_base_quantity -= base
            if batch.remaining_base_quantity <= 0:
                batch.remaining_base_quantity = 0
                batch.is_active = False
    db.session.add(AuditLog(
        user_id=user.id,
        action='STOCK_' + tx_type,
        entity_type='Item',
        entity_id=str(item.id),
        message=f'{tx_type}: {quantity} unit(s) of {item.name}',
        after_data={'reference': tx.reference, 'balance_after': after, 'base_quantity': base},
    ))
    db.session.commit()
    return tx

def decompose(item, base_qty):
    levels = sorted((p for p in item.packaging_levels if p.is_active), key=lambda x: x.base_quantity, reverse=True)
    remaining = int(base_qty)
    parts = []
    for p in levels:
        if p.base_quantity <= 1:
            continue
        n, remaining = divmod(remaining, p.base_quantity)
        if n:
            parts.append(f'{n} {p.unit.name}{"s" if n != 1 else ""}')
    if remaining:
        parts.append(f'{remaining} {item.base_unit.name}{"s" if remaining != 1 else ""}')
    if parts:
        return ' · '.join(parts)
    return f'0 {item.base_unit.name}{"s" if item.base_unit.name.lower() not in {"equipment"} else ""}'
