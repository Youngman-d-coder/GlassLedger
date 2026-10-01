from datetime import date
from flask import Blueprint,render_template
from flask_login import login_required
from ..models import Item,StockTransaction,Notification
from ..services.inventory import current_balance
from ..services.intelligence import dashboard_intelligence
from ..services.notifications import refresh_notifications
bp=Blueprint('dashboard',__name__)
@bp.get('/')
@login_required
def index():
    items=Item.query.filter_by(is_active=True).all(); intel=dashboard_intelligence(items); refresh_notifications()
    metrics={'total_items':len(items),'low_stock':sum(1 for x in intel if x['item'].minimum_stock_base and 0<x['balance']<=x['item'].minimum_stock_base),'out_of_stock':sum(1 for x in intel if x['balance']<=0),'expiring_soon':sum(1 for x in intel if x['expiry'])}
    return render_template('dashboard/index.html',metrics=metrics,recent_transactions=StockTransaction.query.order_by(StockTransaction.occurred_at.desc()).limit(8).all(),today=date.today(),intelligence=intel,notifications=Notification.query.filter_by(is_read=False).order_by(Notification.created_at.desc()).limit(6).all(),page_title='Command Center')
