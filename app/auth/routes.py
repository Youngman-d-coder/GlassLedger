from datetime import datetime, timezone, timedelta
from flask import Blueprint, flash, redirect, render_template, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from ..extensions import db, login_manager
from ..models import User, LoginGuard
from .forms import LoginForm

bp = Blueprint('auth', __name__, url_prefix='/auth')
MAX_FAILURES = 5
LOCK_MINUTES = 10

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def _guard_key(username):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    return f'{ip}:{username}'[:180]

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        key = _guard_key(username)
        guard = LoginGuard.query.filter_by(key=key).first()
        now = datetime.now(timezone.utc)
        if guard and guard.locked_until:
            locked = guard.locked_until if guard.locked_until.tzinfo else guard.locked_until.replace(tzinfo=timezone.utc)
            if locked > now:
                flash('Too many failed sign-in attempts. Try again in a few minutes.', 'error')
                return render_template('auth/login.html', form=form), 429
        user = User.query.filter_by(username=username, is_active=True).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            if guard:
                guard.failures = 0
                guard.locked_until = None
            user.last_login_at = now
            db.session.commit()
            login_user(user, remember=form.remember.data)
            session.permanent = True
            return redirect(url_for('dashboard.index'))
        if not guard:
            guard = LoginGuard(key=key, failures=0)
            db.session.add(guard)
        guard.failures += 1
        if guard.failures >= MAX_FAILURES:
            guard.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            guard.failures = 0
        db.session.commit()
        flash('Username or password is incorrect.', 'error')
    return render_template('auth/login.html', form=form)

@bp.post('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Signed out successfully.', 'success')
    return redirect(url_for('auth.login'))
