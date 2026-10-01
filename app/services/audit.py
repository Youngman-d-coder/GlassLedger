from ..extensions import db
from ..models import AuditLog
def audit(user,action,entity_type,entity_id=None,message=None,before=None,after=None):
    db.session.add(AuditLog(user_id=getattr(user,'id',None),action=action,entity_type=entity_type,entity_id=str(entity_id) if entity_id else None,message=message,before_data=before,after_data=after)); db.session.commit()
