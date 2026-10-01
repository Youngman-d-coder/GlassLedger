from datetime import datetime, timezone, timedelta, date
from statistics import mean, pstdev
from math import ceil
from ..models import StockTransaction, AppSetting
from .inventory import current_balance, packaging_for

USAGE_OUT = {'ISSUE', 'DAMAGED', 'EXPIRED', 'RETURN_OUT'}

def _setting_int(key, default):
    row = AppSetting.query.filter_by(key=key).first()
    try:
        return int(row.value) if row and row.value is not None else default
    except (TypeError, ValueError):
        return default

def _usage(item_id, days=30, offset_days=0):
    end = datetime.now(timezone.utc) - timedelta(days=offset_days)
    start = end - timedelta(days=days)
    txs = StockTransaction.query.filter(
        StockTransaction.item_id == item_id,
        StockTransaction.transaction_type.in_(USAGE_OUT),
        StockTransaction.occurred_at >= start,
        StockTransaction.occurred_at < end,
    ).order_by(StockTransaction.occurred_at.asc()).all()
    return sum(t.base_quantity for t in txs), txs

def preferred_reorder_unit(item):
    unit_id = item.preferred_requisition_unit_id or item.preferred_receive_unit_id
    if unit_id:
        try:
            return unit_id, packaging_for(item, unit_id)
        except ValueError:
            pass
    active = sorted((p for p in item.packaging_levels if p.is_active), key=lambda p: p.base_quantity, reverse=True)
    if active:
        return active[0].unit_id, active[0].base_quantity
    return item.base_unit_id, 1

def insight(item):
    balance = current_balance(item.id)
    horizon = _setting_int('forecast_horizon_days', 30)
    safety_pct = _setting_int('safety_buffer_pct', 20)
    used30, txs = _usage(item.id, 30)
    used7, _ = _usage(item.id, 7)
    used_prev23, _ = _usage(item.id, 23, offset_days=7)
    daily = used30 / 30 if used30 else 0
    recent_daily = used7 / 7 if used7 else 0
    previous_daily = used_prev23 / 23 if used_prev23 else 0
    days_left = balance / daily if daily else None

    demand_target = ceil(daily * horizon * (1 + safety_pct / 100)) if daily else 0
    configured_target = max(item.target_stock_base or 0, item.minimum_stock_base or 0)
    recommended_target = max(configured_target, demand_target)
    reorder_base = max(0, recommended_target - balance)
    reorder_unit_id, reorder_factor = preferred_reorder_unit(item)
    reorder_qty = ceil(reorder_base / reorder_factor) if reorder_base else 0

    trend = None
    if previous_daily:
        trend = ((recent_daily / previous_daily) - 1) * 100
    elif recent_daily:
        trend = 100.0

    anomalies = []
    if len(txs) >= 5:
        previous = [t.base_quantity for t in txs[:-1]]
        if len(previous) >= 4:
            m = mean(previous)
            s = pstdev(previous)
            latest = txs[-1].base_quantity
            threshold = m + (2 * s if s else max(1, m))
            if latest > threshold:
                anomalies.append('Latest issue is unusually large compared with recent usage.')

    expiry = []
    today = date.today()
    for batch in item.batches:
        if batch.expiry_date and batch.remaining_base_quantity > 0:
            days = (batch.expiry_date - today).days
            projected_use = daily * max(days, 0)
            waste_risk = daily > 0 and batch.remaining_base_quantity > projected_use
            if days <= item.expiry_warning_days or waste_risk:
                expiry.append({
                    'batch': batch.batch_number or 'Unlabelled',
                    'days': days,
                    'qty': batch.remaining_base_quantity,
                    'waste_risk': waste_risk,
                    'batch_id': batch.id,
                })
    expiry.sort(key=lambda x: x['days'])

    return {
        'balance': balance,
        'daily_usage': daily,
        'days_left': days_left,
        'reorder_base': reorder_base,
        'reorder_qty': reorder_qty,
        'reorder_unit_id': reorder_unit_id,
        'recommended_target': recommended_target,
        'trend_pct': trend,
        'anomalies': anomalies,
        'expiry': expiry,
        'priority_batch': expiry[0] if expiry else None,
        'safety_pct': safety_pct,
        'horizon_days': horizon,
    }

def dashboard_intelligence(items):
    return [dict(insight(item), item=item) for item in items]
