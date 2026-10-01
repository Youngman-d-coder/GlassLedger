from ..extensions import db
from .core import TimestampMixin
class Item(TimestampMixin,db.Model):
    __tablename__='items'; id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(180),unique=True,nullable=False,index=True)
    slug=db.Column(db.String(200),unique=True,nullable=False,index=True); sku=db.Column(db.String(80),unique=True); description=db.Column(db.Text)
    category_id=db.Column(db.Integer,db.ForeignKey('categories.id'),nullable=False); base_unit_id=db.Column(db.Integer,db.ForeignKey('units.id'),nullable=False)
    minimum_stock_base=db.Column(db.Integer,nullable=False,default=0); critical_stock_base=db.Column(db.Integer,nullable=False,default=0); target_stock_base=db.Column(db.Integer,nullable=False,default=0)
    expiry_warning_days=db.Column(db.Integer,nullable=False,default=30); expiry_tracking=db.Column(db.Boolean,nullable=False,default=False); batch_tracking=db.Column(db.Boolean,nullable=False,default=False)
    preferred_receive_unit_id=db.Column(db.Integer,db.ForeignKey('units.id')); preferred_issue_unit_id=db.Column(db.Integer,db.ForeignKey('units.id')); preferred_display_unit_id=db.Column(db.Integer,db.ForeignKey('units.id')); preferred_requisition_unit_id=db.Column(db.Integer,db.ForeignKey('units.id'))
    is_active=db.Column(db.Boolean,nullable=False,default=True)
    category=db.relationship('Category',backref='items'); base_unit=db.relationship('Unit',foreign_keys=[base_unit_id])
class ItemAlias(db.Model):
    __tablename__='item_aliases'; id=db.Column(db.Integer,primary_key=True); item_id=db.Column(db.Integer,db.ForeignKey('items.id'),nullable=False,index=True); alias=db.Column(db.String(180),nullable=False); normalized_alias=db.Column(db.String(180),unique=True,nullable=False,index=True)
    item=db.relationship('Item',backref=db.backref('aliases',cascade='all, delete-orphan'))
class ItemPackaging(TimestampMixin,db.Model):
    __tablename__='item_packaging'; __table_args__=(db.UniqueConstraint('item_id','unit_id',name='uq_item_packaging_unit'),db.CheckConstraint('base_quantity > 0',name='ck_packaging_base_positive'))
    id=db.Column(db.Integer,primary_key=True); item_id=db.Column(db.Integer,db.ForeignKey('items.id'),nullable=False,index=True); unit_id=db.Column(db.Integer,db.ForeignKey('units.id'),nullable=False)
    parent_packaging_id=db.Column(db.Integer,db.ForeignKey('item_packaging.id')); quantity_in_parent=db.Column(db.Integer); base_quantity=db.Column(db.Integer,nullable=False); sort_order=db.Column(db.Integer,default=0,nullable=False); is_active=db.Column(db.Boolean,default=True,nullable=False)
    item=db.relationship('Item',backref=db.backref('packaging_levels',cascade='all, delete-orphan')); unit=db.relationship('Unit'); parent=db.relationship('ItemPackaging',remote_side=[id],backref='children')
