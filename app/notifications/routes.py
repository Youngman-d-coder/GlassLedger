from flask import Blueprint,render_template,redirect,url_for
from flask_login import login_required
from ..extensions import db
from ..models import Notification
from ..services.notifications import refresh_notifications
bp=Blueprint('notifications',__name__,url_prefix='/notifications')
@bp.get('/')
@login_required
def index(): refresh_notifications(); return render_template('notifications/index.html',notifications=Notification.query.order_by(Notification.created_at.desc()).all(),page_title='Notifications')
@bp.post('/read-all')
@login_required
def read_all(): Notification.query.update({'is_read':True}); db.session.commit(); return redirect(url_for('notifications.index'))
