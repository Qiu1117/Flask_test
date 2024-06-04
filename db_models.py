from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as db
from sqlalchemy import func, Integer, String, SmallInteger, Text, Time, Date, Enum
from sqlalchemy.sql.schema import ForeignKey, UniqueConstraint
from sqlalchemy.sql.sqltypes import Boolean, Numeric, DateTime
from sqlalchemy.dialects.postgresql import JSON, JSONB, ARRAY, ENUM
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


db = SQLAlchemy()

class TimeBaseModel(db.Model):
    __abstract__ = True  # must add this in flask-sqlachemy

    create_time = db.Column(DateTime, nullable=False, default=func.now())  
    update_time = db.Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())  

Base = declarative_base(cls=TimeBaseModel)


class Dataset_Group(Base):
    __tablename__ = "Dataset_Group"

    dataset_id = db.Column(
        Integer, ForeignKey("Dataset.id", ondelete="CASCADE"), primary_key=True
    )
    group_id = db.Column(
        Integer, ForeignKey("Group.id", ondelete="CASCADE"), primary_key=True
    )
    valid = db.Column(Boolean, default=True)


class Acc_Group(Base):
    __tablename__ = "Acc_Group"

    acc_id = db.Column(Integer, ForeignKey("Account.id"), primary_key=True)
    group_id = db.Column(Integer, ForeignKey("Group.id"), primary_key=True)
    editable = db.Column(Boolean)
    can_upload_dataset = db.Column(Boolean)
    is_owner = db.Column(Boolean)
    status = db.Column(Numeric(1))  # 0: enable , 1: pending, 2: disable


class Account(Base):
    __tablename__ = "Account"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    username = db.Column(String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(String(256))
    email = db.Column(String(120))
    role = db.Column(Numeric(1, 0))
    expiration_time = db.Column(DateTime)
    notification = db.Column(JSONB, server_default="{}")

    has_group = db.relationship("Group", backref="belongs")
    paired_with_group = db.relationship("Acc_Group", backref="belongs_user")


class Group(Base):
    __tablename__ = 'Group'

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    group_name = db.Column(String(80), nullable=False, index=True)
    description = db.Column(Text)
    owner = db.Column(Integer, ForeignKey(Account.id))
    valid = db.Column(Boolean, default=True)

    contains_user = db.relationship('Acc_Group', backref='belongs')
    contains_dataset = db.relationship('Dataset_Group', backref='belongs')


class Dataset(Base):
    __tablename__ = "Dataset"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    dataset_name = db.Column(String(100), nullable=False, index=True)
    description = db.Column(Text)
    valid = db.Column(Boolean, default=True)
    modalities = db.Column(ARRAY(String(30)))
    labels = db.Column(ARRAY(String(30)))

    owner = db.Column(Integer, ForeignKey(Account.id))
    belongto_acc = relationship("Account", backref="contains")


class Patient(Base):
    __tablename__ = "Patient"
    
    patient_orthanc_id = db.Column(String(64), primary_key=True)  
    
    patient_id = db.Column(String(30))
    patient_name = db.Column(String(50))
    patient_sex = db.Column(String(10))
    patient_birthdate = db.Column(String(10))

    valid = db.Column(Boolean, default=True)


class Dataset_Patients(Base):
    __tablename__ = "Dataset_Patients"

    D_P_pair_id = db.Column(Integer, autoincrement=True, primary_key=True)
    patient_orthanc_id = db.Column(String(64), ForeignKey(Patient.patient_orthanc_id))
    dataset_id = db.Column(Integer, ForeignKey(Dataset.id))

    valid = db.Column(Boolean, default=True)

    __table_args__ = (UniqueConstraint(dataset_id, patient_orthanc_id),)


class Dataset_Studies(Base):
    __tablename__ = "Dataset_Studies"

    DP_S_pair_id = db.Column(Integer, autoincrement=True, primary_key=True)
    D_P_pair_id = db.Column(Integer, ForeignKey(Dataset_Patients.D_P_pair_id))
    dataset_id = db.Column(Integer, ForeignKey(Dataset.id))
    patient_orthanc_id = db.Column(String(64), ForeignKey(Patient.patient_orthanc_id))
    study_orthanc_id = db.Column(String(64))

    valid = db.Column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint(dataset_id, patient_orthanc_id, study_orthanc_id),
    )


class Dataset_Series(Base):
    __tablename__ = "Dataset_Series"

    DPS_S_pair_id = db.Column(Integer, autoincrement=True, primary_key=True)
    DP_S_pair_id = db.Column(Integer, ForeignKey(Dataset_Studies.DP_S_pair_id))

    dataset_id = db.Column(Integer, ForeignKey(Dataset.id))
    patient_orthanc_id = db.Column(String(64), ForeignKey(Patient.patient_orthanc_id))
    study_orthanc_id = db.Column(String(64))
    series_orthanc_id = db.Column(String(64))

    valid = db.Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint(
            dataset_id, patient_orthanc_id, study_orthanc_id, series_orthanc_id
        ),
    )


class Dataset_Instances(Base):
    __tablename__ = "Dataset_Instances"

    series_orthanc_id = db.Column(String(64))
    instance_orthanc_id = db.Column(String(64),primary_key=True)

    status = db.Column(Numeric(1)) 
