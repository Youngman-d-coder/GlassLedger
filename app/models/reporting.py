from ..extensions import db
from .core import TimestampMixin

class Requisition(TimestampMixin, db.Model):
    __tablename__ = 'requisitions'
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(80), unique=True, nullable=False, index=True)
    period_month = db.Column(db.Integer, nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='DRAFT')
    prepared_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notes = db.Column(db.Text)
    prepared_by = db.relationship('User')

class RequisitionItem(db.Model):
    __tablename__ = 'requisition_items'
    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey('requisitions.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    current_stock_base = db.Column(db.Integer, nullable=False, default=0)
    average_usage_base = db.Column(db.Integer, nullable=False, default=0)
    target_stock_base = db.Column(db.Integer, nullable=False, default=0)
    suggested_quantity = db.Column(db.Integer)
    suggested_unit_id = db.Column(db.Integer, db.ForeignKey('units.id'))
    requested_quantity = db.Column(db.Integer)
    requested_unit_id = db.Column(db.Integer, db.ForeignKey('units.id'))
    reason_or_note = db.Column(db.Text)
    requisition = db.relationship('Requisition', backref=db.backref('items', cascade='all, delete-orphan'))
    item = db.relationship('Item')
    suggested_unit = db.relationship('Unit', foreign_keys=[suggested_unit_id])
    requested_unit = db.relationship('Unit', foreign_keys=[requested_unit_id])

class Report(TimestampMixin, db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(100), unique=True, nullable=False, index=True)
    report_type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    date_from = db.Column(db.Date)
    date_to = db.Column(db.Date)
    generated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), index=True)
    notes = db.Column(db.Text)
    html_path = db.Column(db.String(500))
    pdf_path = db.Column(db.String(500))
    file_hash = db.Column(db.String(128))
    snapshot_json = db.Column(db.JSON)
    is_finalized = db.Column(db.Boolean, nullable=False, default=False)
    parent_report_id = db.Column(db.Integer, db.ForeignKey('reports.id'))
    revision = db.Column(db.Integer, nullable=False, default=0)
    generated_by = db.relationship('User')
    item = db.relationship('Item')
    parent = db.relationship('Report', remote_side=[id], backref='revisions')

class SharedReport(TimestampMixin, db.Model):
    __tablename__ = 'shared_reports'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(128), unique=True, nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))
    allow_download = db.Column(db.Boolean, nullable=False, default=False)
    access_count = db.Column(db.Integer, nullable=False, default=0)
    last_accessed_at = db.Column(db.DateTime(timezone=True))
    report = db.relationship('Report', backref='shared_links')
    created_by = db.relationship('User')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    entity_type = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.String(80), index=True)
    before_data = db.Column(db.JSON)
    after_data = db.Column(db.JSON)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    user = db.relationship('User')
