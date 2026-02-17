from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

# Convention for naming constraints to match database standards
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy()

# Import all models here so SQLAlchemy is aware of them
# This is crucial for flask db migrate to detect tables correctly
from .user import User, ActivityLog
from .staff import Staff, StaffImage
from .visitor import Visitor, VisitorSession, VisitorImage
from .camera import Camera, SystemSettings