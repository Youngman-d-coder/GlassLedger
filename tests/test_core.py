from pathlib import Path
import tempfile
import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User, Category, Unit, Item, ItemPackaging, AppSetting
from app.services.inventory import record_movement, current_balance, decompose
from app.services.intelligence import insight
from app.services.backups import create_backup, integrity


@pytest.fixture()
def app(tmp_path):
    db_file = tmp_path / 'test.db'
    backup_dir = tmp_path / 'backups'
    report_dir = tmp_path / 'reports'
    class TestConfig:
        TESTING = True
        SECRET_KEY = 'test-secret'
        WTF_CSRF_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_file}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        BACKUP_DIR = str(backup_dir)
        REPORT_DIR = str(report_dir)
        GOOGLE_SERVICE_ACCOUNT_FILE = None
        GOOGLE_DRIVE_FOLDER_ID = None
        AUTO_DRIVE_BACKUP = False
        PERMANENT_SESSION_LIFETIME = __import__('datetime').timedelta(minutes=30)
        APP_VERSION = 'test'
        MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        owner = User(username='owner', display_name='Owner', email='owner@example.com', password_hash=generate_password_hash('password123'), role='OWNER')
        cat = Category(name='Laboratory Consumables', slug='laboratory-consumables')
        piece = Unit(name='Piece', unit_type='COUNT')
        pack = Unit(name='Pack', unit_type='PACKAGING')
        db.session.add_all([owner, cat, piece, pack, AppSetting(key='onboarding_complete', value='1'), AppSetting(key='safety_buffer_pct', value='20'), AppSetting(key='forecast_horizon_days', value='30')])
        db.session.commit()
        item = Item(name='EDTA Tube', slug='edta-tube', category_id=cat.id, base_unit_id=piece.id, minimum_stock_base=100, target_stock_base=500, preferred_receive_unit_id=pack.id, preferred_issue_unit_id=pack.id, preferred_requisition_unit_id=pack.id)
        db.session.add(item); db.session.flush()
        db.session.add_all([ItemPackaging(item_id=item.id, unit_id=piece.id, base_quantity=1), ItemPackaging(item_id=item.id, unit_id=pack.id, base_quantity=100)])
        db.session.commit()
    yield app


def test_multi_unit_stock_math(app):
    with app.app_context():
        owner = User.query.filter_by(username='owner').first(); item = Item.query.filter_by(name='EDTA Tube').first(); pack = Unit.query.filter_by(name='Pack').first()
        record_movement(item, 'RECEIPT', 5, pack.id, owner)
        assert current_balance(item.id) == 500
        record_movement(item, 'ISSUE', 2, pack.id, owner)
        assert current_balance(item.id) == 300
        assert '3 Packs' in decompose(item, 300)
        with pytest.raises(ValueError): record_movement(item, 'ISSUE', 4, pack.id, owner)


def test_reorder_intelligence(app):
    with app.app_context():
        owner = User.query.filter_by(username='owner').first(); item = Item.query.filter_by(name='EDTA Tube').first(); pack = Unit.query.filter_by(name='Pack').first()
        record_movement(item, 'RECEIPT', 2, pack.id, owner)
        data = insight(item)
        assert data['balance'] == 200
        assert data['reorder_base'] >= 300
        assert data['reorder_qty'] >= 3


def test_backup_is_valid_sqlite(app):
    with app.app_context():
        rec = create_backup('test')
        path = Path(app.config['BACKUP_DIR']) / rec.filename
        assert path.exists()
        assert integrity(path)
        assert rec.status == 'HEALTHY'


def test_login_and_inventory_page(app):
    client = app.test_client()
    response = client.post('/auth/login', data={'username':'owner','password':'password123'}, follow_redirects=True)
    assert response.status_code == 200
    response = client.get('/inventory/')
    assert response.status_code == 200
    assert b'EDTA Tube' in response.data
