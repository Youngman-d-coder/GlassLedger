from ..extensions import db
from .core import TimestampMixin
class StockBatch(TimestampMixin,db.Model):
    __tablename__='stock_batches'; id=db.Column(db.Integer,primary_key=True); item_id=db.Column(db.Integer,db.ForeignKey('items.id'),nullable=False,index=True)
    batch_number=db.Column(db.String(120),index=True); expiry_date=db.Column(db.Date); initial_base_quantity=db.Column(db.Integer,default=0,nullable=False); remaining_base_quantity=db.Column(db.Integer,default=0,nullable=False); supplier=db.Column(db.String(180)); notes=db.Column(db.Text); is_active=db.Column(db.Boolean,default=True,nullable=False)
    item=db.relationship('Item',backref='batches')
class StockTransaction(TimestampMixin,db.Model):
    __tablename__='stock_transactions'; __table_args__=(db.CheckConstraint('entered_quantity > 0',name='ck_tx_qty_positive'),db.CheckConstraint('base_quantity > 0',name='ck_tx_base_positive'))
    id=db.Column(db.Integer,primary_key=True); reference=db.Column(db.String(80),unique=True,nullable=False,index=True); item_id=db.Column(db.Integer,db.ForeignKey('items.id'),nullable=False,index=True); batch_id=db.Column(db.Integer,db.ForeignKey('stock_batches.id'),index=True)
    transaction_type=db.Column(db.String(40),nullable=False,index=True); entered_quantity=db.Column(db.Integer,nullable=False); entered_unit_id=db.Column(db.Integer,db.ForeignKey('units.id'),nullable=False); base_quantity=db.Column(db.Integer,nullable=False)
    balance_before=db.Column(db.Integer,nullable=False); balance_after=db.Column(db.Integer,nullable=False); department_or_destination=db.Column(db.String(180)); purpose=db.Column(db.String(255)); notes=db.Column(db.Text); performed_by_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False); occurred_at=db.Column(db.DateTime(timezone=True),nullable=False)
    item=db.relationship('Item',backref='transactions'); batch=db.relationship('StockBatch',backref='transactions'); entered_unit=db.relationship('Unit'); performed_by=db.relationship('User')
class StockAdjustment(TimestampMixin,db.Model):
    __tablename__='stock_adjustments'; id=db.Column(db.Integer,primary_key=True); transaction_id=db.Column(db.Integer,db.ForeignKey('stock_transactions.id'),unique=True,nullable=False); reason_code=db.Column(db.String(80),nullable=False); reason_text=db.Column(db.Text); system_quantity=db.Column(db.Integer,nullable=False); physical_quantity=db.Column(db.Integer,nullable=False); difference=db.Column(db.Integer,nullable=False); created_by_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    transaction=db.relationship('StockTransaction',backref=db.backref('adjustment',uselist=False)); created_by=db.relationship('User')
