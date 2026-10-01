from pathlib import Path
from time import time
from dotenv import load_dotenv
from flask import Flask, redirect, url_for, request, session, flash
from flask_login import current_user, logout_user
from .config import Config
from .extensions import csrf, db, login_manager, migrate

PUBLIC_ENDPOINTS = {'auth.login', 'auth.logout', 'static', 'reports.shared', 'reports.shared_download'}

def create_app(config_class=Config):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config['BACKUP_DIR']).mkdir(parents=True, exist_ok=True)
    Path(app.config['REPORT_DIR']).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please sign in to continue.'
    login_manager.login_message_category = 'info'

    from . import models
    from .auth.routes import bp as auth
    from .dashboard.routes import bp as dash
    from .inventory.routes import bp as inv
    from .transactions.routes import bp as tx
    from .settings.routes import bp as settings
    from .notifications.routes import bp as notes
    from .requisitions.routes import bp as req
    from .reports.routes import bp as reports
    from .onboarding.routes import bp as onboard
    for b in [auth, dash, inv, tx, settings, notes, req, reports, onboard]:
        app.register_blueprint(b)

    from .cli import register_commands
    register_commands(app)

    @app.before_request
    def security_and_first_run():
        endpoint = request.endpoint
        if endpoint == 'static':
            return None
        if current_user.is_authenticated:
            session.permanent = True
            now = time()
            last = session.get('_last_active')
            timeout = app.config['PERMANENT_SESSION_LIFETIME'].total_seconds()
            if last and now - last > timeout and endpoint not in {'auth.logout'}:
                logout_user()
                session.clear()
                flash('Your session expired after inactivity. Please sign in again.', 'info')
                return redirect(url_for('auth.login'))
            session['_last_active'] = now

        if not current_user.is_authenticated or endpoint in PUBLIC_ENDPOINTS or endpoint == 'onboarding.index':
            return None

        from .models import AppSetting
        complete = AppSetting.query.filter_by(key='onboarding_complete', value='1').first()
        if not complete:
            return redirect(url_for('onboarding.index'))

        # Cheap once-per-day safety backup. If the app slept all day, there were no writes to protect.
        if endpoint not in {'settings.restore', 'settings.backup', 'settings.import_backup'}:
            try:
                from .services.backups import ensure_daily_backup
                ensure_daily_backup()
            except Exception:
                app.logger.exception('Automatic backup check failed')
        return None

    @app.context_processor
    def globals_for_templates():
        return {'app_version': app.config['APP_VERSION']}

    return app
