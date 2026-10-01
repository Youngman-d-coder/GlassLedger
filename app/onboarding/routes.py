from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Category, Unit, AppSetting, Item, ItemPackaging
from ..services.text import normalize_name, slugify
from ..services.inventory import record_movement

bp = Blueprint('onboarding', __name__, url_prefix='/onboarding')
DEFAULT_UNITS = ['Piece','Pack','Bag','Box','Carton','Bottle','Roll','Ream','Kit','Tube','Sheet','Pair']
DEFAULT_CATS = ['Laboratory Consumables','Laboratory Reagents','Rapid Test Kits','PPE','Waste Management','Cleaning Supplies','Stationery','Equipment']

def _set(key, value):
    s = AppSetting.query.filter_by(key=key).first() or AppSetting(key=key)
    s.value = str(value); db.session.add(s)

def ensure_defaults():
    for name in DEFAULT_UNITS:
        if not Unit.query.filter_by(name=name).first():
            db.session.add(Unit(name=name, unit_type='PACKAGING' if name not in ['Piece','Tube','Sheet'] else 'COUNT'))
    for name in DEFAULT_CATS:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name, slug=slugify(name)))
    if not AppSetting.query.filter_by(key='safety_buffer_pct').first(): _set('safety_buffer_pct', '20')
    if not AppSetting.query.filter_by(key='forecast_horizon_days').first(): _set('forecast_horizon_days', '30')
    db.session.commit()

def finish():
    _set('onboarding_complete', '1'); db.session.commit()
    flash('GlassLedger setup complete. Everything remains editable in Settings.', 'success')
    return redirect(url_for('dashboard.index'))

@bp.route('/', methods=['GET','POST'])
@login_required
def index():
    step = request.args.get('step', 1, type=int)
    ensure_defaults()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'profile':
            _set('organization_name', request.form.get('organization_name','').strip())
            _set('department_name', request.form.get('department_name','').strip())
            db.session.commit(); return redirect(url_for('onboarding.index', step=2))
        if action == 'skip-products':
            return finish()
        if action == 'product':
            name = normalize_name(request.form.get('name'))
            if not name: flash('Enter a product name or skip this step.', 'error')
            else:
                base_unit_id = int(request.form['base_unit_id'])
                item = Item(name=name, slug=slugify(name), category_id=int(request.form['category_id']), base_unit_id=base_unit_id, expiry_tracking=bool(request.form.get('expiry_tracking')), batch_tracking=bool(request.form.get('batch_tracking')), preferred_receive_unit_id=base_unit_id, preferred_issue_unit_id=base_unit_id, preferred_display_unit_id=base_unit_id, preferred_requisition_unit_id=base_unit_id)
                db.session.add(item); db.session.flush(); db.session.add(ItemPackaging(item_id=item.id, unit_id=base_unit_id, base_quantity=1)); db.session.commit()
                return redirect(url_for('onboarding.index', step=3, item_id=item.id))
        if action == 'stock':
            item = Item.query.get_or_404(request.form.get('item_id', type=int))
            for idx in range(1,4):
                unit_id = request.form.get(f'pack_unit_{idx}', type=int); factor = request.form.get(f'pack_factor_{idx}', type=int)
                if unit_id and factor and unit_id != item.base_unit_id and factor > 1:
                    row = ItemPackaging.query.filter_by(item_id=item.id, unit_id=unit_id).first() or ItemPackaging(item_id=item.id, unit_id=unit_id)
                    row.base_quantity = factor; row.sort_order = factor; row.is_active = True; db.session.add(row)
            db.session.commit()
            qty = request.form.get('opening_qty', type=int) or 0; unit_id = request.form.get('opening_unit_id', type=int)
            if qty > 0 and unit_id:
                try: record_movement(item, 'OPENING_BALANCE', qty, unit_id, current_user, purpose='Opening stock from first-run setup')
                except ValueError as exc: flash(str(exc), 'error'); return redirect(url_for('onboarding.index', step=3, item_id=item.id))
            return finish()
    item = Item.query.get(request.args.get('item_id', type=int)) if step == 3 else None
    return render_template('onboarding/index.html', step=step, item=item, categories=Category.query.filter_by(is_active=True).order_by(Category.name).all(), units=Unit.query.filter_by(is_active=True).order_by(Unit.name).all(), page_title='Welcome to GlassLedger')
