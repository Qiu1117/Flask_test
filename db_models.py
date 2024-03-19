from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as db
from decimal import Clamped
import enum
from sqlalchemy import func, Integer, String, SmallInteger, Text, Time, Date, Enum
from sqlalchemy.sql.schema import ForeignKey, UniqueConstraint
from sqlalchemy.sql.sqltypes import Boolean, Numeric, DateTime
from sqlalchemy.dialects.postgresql import JSON, JSONB, ARRAY, ENUM
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import relationship



db = SQLAlchemy()

class TimeBaseModel(db.Model):
    __abstract__ = True  # must add this in flask-sqlachemy

    create_time = db.Column(DateTime, nullable=False, default=func.now())  
    update_time = db.Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())  

Base = declarative_base(cls=TimeBaseModel)



class Dataset_Group(Base):
    __tablename__ = 'Dataset_Group'

    dataset_id = db.Column(Integer, ForeignKey('Dataset.id'), primary_key=True)
    group_id = db.Column(Integer, ForeignKey('Group.id'), primary_key=True)
    valid = db.Column(Boolean, default=True)


class Acc_Group(Base):
    __tablename__ = 'Acc_Group'

    acc_id = db.Column(Integer, ForeignKey('Account.id'), primary_key=True)
    group_id = db.Column(Integer, ForeignKey('Group.id'), primary_key=True)
    editable = db.Column(Boolean)
    can_upload_dataset = db.Column(Boolean)
    owner = db.Column(Boolean)
    status = db.Column(Numeric(1))   # 0: enable , 1: pending, 2: disable
    

class Account(Base):
    __tablename__ = 'Account'

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    username = db.Column(String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(String(256))
    email = db.Column(String(120))
    role = db.Column(Numeric(1,0))
    expiration_time = db.Column(DateTime)
    notification = db.Column(JSON)


class Archive(Base):
    __tablename__ = 'Archive'

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    archive_name = db.Column(String(40), nullable=False, index=True)
    description = db.Column(Text)
    research_focus = db.Column(Text)
    root_link = db.Column(String(300))
    paper_link = db.Column(String(300))
    total_case_amount = db.Column(Integer)
    recorded_amount = db.Column(Integer)
    crawlable = db.Column(Boolean)
    upload_features = db.Column(Text)
    download_features = db.Column(Text)


class Dataset(Base):
    __tablename__ = 'Dataset'

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    dataset_name = db.Column(String(100), nullable=False, index=True)
    description = db.Column(Text)
    research_focus = db.Column(Text)
    root_link = db.Column(String(300))
    paper_link = db.Column(String(300))
    upload_date = db.Column(DateTime)
    download_times = db.Column(Integer)
    size = db.Column(String(20))
    modalities = db.Column(ARRAY(String(30)))
    participant_amount = db.Column(Integer)
    file_amount = db.Column(Integer)
    others = db.Column(JSON)
    labels = db.Column(ARRAY(String(30)))

    owner = db.Column(Integer, ForeignKey(Account.id))
    belongto_acc = relationship('Account', backref="contains")

    archive_id = db.Column(Integer, ForeignKey(Archive.id))
    belongto_arc = relationship('Archive', backref="contains")


class Group(Base):
    __tablename__ = 'Group'
    
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    group_name = db.Column(String(80), nullable=False, index=True)
    description = db.Column(Text)
    valid = db.Column(Boolean, default=True)

    contains_user = db.relationship('Acc_Group', backref='belongs')
    contains_dataset = db.relationship('Dataset_Group', backref='belongs')

