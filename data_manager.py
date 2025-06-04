from sqlalchemy import and_
from flask import abort
from db_models import (
    db, Dataset_Patients, Dataset_Studies, Dataset_Series, 
    Dataset_Instances, Patient, Study, Series
)
from orthanc_utils import get_patient_info, get_study_info, get_series_info


def _new_study(orthanc_data):
    study_orthanc_id = orthanc_data["ParentStudy"]
    study_info = get_study_info(study_orthanc_id)
    main_dicom_tags = study_info.get("MainDicomTags", {})

    new_study = Study(
        study_orthanc_id=study_orthanc_id,
        study_instance_uid=main_dicom_tags.get("StudyInstanceUID", ""),
        study_date=main_dicom_tags.get("StudyDate", ""),
        study_time=main_dicom_tags.get("StudyTime", ""),
        study_id=main_dicom_tags.get("StudyID", ""),
        study_description=main_dicom_tags.get("StudyDescription", ""),
        accession_number=main_dicom_tags.get("AccessionNumber", ""),
        requested_procedure_description=main_dicom_tags.get("RequestedProcedureDescription", ""),
        institution_name=main_dicom_tags.get("InstitutionName", ""),
        requesting_physician=main_dicom_tags.get("RequestingPhysician", ""),
        referring_physician_name=main_dicom_tags.get("ReferringPhysicianName", ""),
    )
    db.session.add(new_study)
    db.session.commit()

def _new_series(orthanc_data):
    series_orthanc_id = orthanc_data["ParentSeries"]
    series_info = get_series_info(series_orthanc_id)
    main_dicom_tags = series_info.get("MainDicomTags", {})

    def safe_int(value):
        try:
            return int(value) if value else None
        except ValueError:
            return None

    new_series = Series(
        series_orthanc_id=series_orthanc_id,
        series_instance_uid=main_dicom_tags.get("SeriesInstanceUID", ""),
        series_date=main_dicom_tags.get("SeriesDate", ""),
        series_time=main_dicom_tags.get("SeriesTime", ""),
        modality=main_dicom_tags.get("Modality", ""),
        manufacturer=main_dicom_tags.get("Manufacturer", ""),
        station_name=main_dicom_tags.get("StationName", ""),
        series_description=main_dicom_tags.get("SeriesDescription", ""),
        body_part_examined=main_dicom_tags.get("BodyPartExamined", ""),
        sequence_name=main_dicom_tags.get("SequenceName", ""),
        protocol_name=main_dicom_tags.get("ProtocolName", ""),
        series_number=safe_int(main_dicom_tags.get("SeriesNumber")),
        cardiac_number_of_images=safe_int(main_dicom_tags.get("CardiacNumberOfImages")),
        images_in_acquisition=safe_int(main_dicom_tags.get("ImagesInAcquisition")),
        number_of_temporal_positions=safe_int(main_dicom_tags.get("NumberOfTemporalPositions")),
        number_of_slices=safe_int(main_dicom_tags.get("NumberOfSlices")),
        number_of_time_slices=safe_int(main_dicom_tags.get("NumberOfTimeSlices")),
        image_orientation_patient=main_dicom_tags.get("ImageOrientationPatient", ""),
        series_type=main_dicom_tags.get("SeriesType", ""),
        operators_name=main_dicom_tags.get("OperatorsName", ""),
        performed_procedure_step_description=main_dicom_tags.get("PerformedProcedureStepDescription", ""),
        acquisition_device_processing_description=main_dicom_tags.get("AcquisitionDeviceProcessingDescription", ""),
        contrast_bolus_agent=main_dicom_tags.get("ContrastBolusAgent", ""),
    )
    db.session.add(new_series)
    db.session.commit()
    

def _new_patient_pair(orthanc_data, dataset_id):  # 保持原函数名
    patient_orthanc_id = orthanc_data["ParentPatient"]
    shared_tags = get_patient_info(patient_orthanc_id)

    patient = Patient.query.filter_by(patient_orthanc_id=patient_orthanc_id).first()
    if patient is None:
        new_patient = Patient(
            patient_orthanc_id=patient_orthanc_id,
            patient_id=shared_tags.get("PatientID", ""),
            patient_name=shared_tags.get("PatientName", ""),
            patient_sex=shared_tags.get("PatientSex", ""),
            patient_birthdate=shared_tags.get("PatientBirthDate", ""),
            patient_weight=shared_tags.get("PatientWeight", ""),
        )
        db.session.add(new_patient)
        db.session.commit()

    new_patient_pair = Dataset_Patients(
        patient_orthanc_id=patient_orthanc_id,
        dataset_id=dataset_id,
    )
    db.session.add(new_patient_pair)
    db.session.commit()

def _new_study_pair(orthanc_data, dataset_id):  # 保持原函数名
    patient_orthanc_id = orthanc_data["ParentPatient"]
    study_orthanc_id = orthanc_data["ParentStudy"]

    patient_pair = Dataset_Patients.query.filter(
        and_(
            Dataset_Patients.patient_orthanc_id == patient_orthanc_id,
            Dataset_Patients.dataset_id == dataset_id,
        )
    ).first()
    if patient_pair is None:
        abort(404, description="Dataset and patient not match")

    study = Study.query.filter_by(study_orthanc_id=study_orthanc_id).first()
    if study is None:
        _new_study(orthanc_data)
    else:
        study.valid = True
        db.session.commit()

    new_study_pair = Dataset_Studies(
        D_P_pair_id=patient_pair.D_P_pair_id,
        patient_orthanc_id=patient_orthanc_id,
        study_orthanc_id=study_orthanc_id,
        dataset_id=dataset_id,
    )
    db.session.add(new_study_pair)
    db.session.commit()

def _new_series_pair(orthanc_data, dataset_id):  # 保持原函数名
    patient_orthanc_id = orthanc_data["ParentPatient"]
    study_orthanc_id = orthanc_data["ParentStudy"]
    series_orthanc_id = orthanc_data["ParentSeries"]

    study_pair = Dataset_Studies.query.filter(
        and_(
            Dataset_Studies.patient_orthanc_id == patient_orthanc_id,
            Dataset_Studies.study_orthanc_id == study_orthanc_id,
            Dataset_Studies.dataset_id == dataset_id,
        )
    ).first()
    if study_pair is None:
        abort(404, description="Dataset-patient and study do not match")

    series = Series.query.filter_by(series_orthanc_id=series_orthanc_id).first()
    if series is None:
        _new_series(orthanc_data)
    else:
        series.valid = True
        db.session.commit()

    new_series_pair = Dataset_Series(
        DP_S_pair_id=study_pair.DP_S_pair_id,
        patient_orthanc_id=patient_orthanc_id,
        study_orthanc_id=study_orthanc_id,
        series_orthanc_id=series_orthanc_id,
        dataset_id=dataset_id,
    )
    db.session.add(new_series_pair)
    db.session.commit()

def _new_instance_pair(orthanc_data):  # 保持原函数名
    series_orthanc_id = orthanc_data["ParentSeries"]
    instance_orthanc_id = orthanc_data["ID"]

    new_instance_pair = Dataset_Instances(
        series_orthanc_id=series_orthanc_id,
        instance_orthanc_id=instance_orthanc_id,
        status=0,
    )
    db.session.add(new_instance_pair)
    db.session.commit()

def create_patient_pair(orthanc_data, dataset_id):
    patient_orthanc_id = orthanc_data["ParentPatient"]
    shared_tags = get_patient_info(patient_orthanc_id)

    patient = Patient.query.filter_by(patient_orthanc_id=patient_orthanc_id).first()
    if patient is None:
        new_patient = Patient(
            patient_orthanc_id=patient_orthanc_id,
            patient_id=shared_tags.get("PatientID", ""),
            patient_name=shared_tags.get("PatientName", ""),
            patient_sex=shared_tags.get("PatientSex", ""),
            patient_birthdate=shared_tags.get("PatientBirthDate", ""),
            patient_weight=shared_tags.get("PatientWeight", ""),
        )
        db.session.add(new_patient)
        db.session.commit()

    new_patient_pair = Dataset_Patients(
        patient_orthanc_id=patient_orthanc_id,
        dataset_id=dataset_id,
    )
    db.session.add(new_patient_pair)
    db.session.commit()


def create_study_pair(orthanc_data, dataset_id):
    patient_orthanc_id = orthanc_data["ParentPatient"]
    study_orthanc_id = orthanc_data["ParentStudy"]

    patient_pair = Dataset_Patients.query.filter(
        and_(
            Dataset_Patients.patient_orthanc_id == patient_orthanc_id,
            Dataset_Patients.dataset_id == dataset_id,
        )
    ).first()
    if patient_pair is None:
        abort(404, description="Dataset and patient not match")

    study = Study.query.filter_by(study_orthanc_id=study_orthanc_id).first()
    if study is None:
        create_study(orthanc_data)
    else:
        study.valid = True
        db.session.commit()

    new_study_pair = Dataset_Studies(
        D_P_pair_id=patient_pair.D_P_pair_id,
        patient_orthanc_id=patient_orthanc_id,
        study_orthanc_id=study_orthanc_id,
        dataset_id=dataset_id,
    )
    db.session.add(new_study_pair)
    db.session.commit()


def create_study(orthanc_data):
    study_orthanc_id = orthanc_data["ParentStudy"]
    study_info = get_study_info(study_orthanc_id)
    main_dicom_tags = study_info.get("MainDicomTags", {})

    new_study = Study(
        study_orthanc_id=study_orthanc_id,
        study_instance_uid=main_dicom_tags.get("StudyInstanceUID", ""),
        study_date=main_dicom_tags.get("StudyDate", ""),
        study_time=main_dicom_tags.get("StudyTime", ""),
        study_id=main_dicom_tags.get("StudyID", ""),
        study_description=main_dicom_tags.get("StudyDescription", ""),
        accession_number=main_dicom_tags.get("AccessionNumber", ""),
        requested_procedure_description=main_dicom_tags.get("RequestedProcedureDescription", ""),
        institution_name=main_dicom_tags.get("InstitutionName", ""),
        requesting_physician=main_dicom_tags.get("RequestingPhysician", ""),
        referring_physician_name=main_dicom_tags.get("ReferringPhysicianName", ""),
    )
    db.session.add(new_study)
    db.session.commit()


def create_series_pair(orthanc_data, dataset_id):
    patient_orthanc_id = orthanc_data["ParentPatient"]
    study_orthanc_id = orthanc_data["ParentStudy"]
    series_orthanc_id = orthanc_data["ParentSeries"]

    study_pair = Dataset_Studies.query.filter(
        and_(
            Dataset_Studies.patient_orthanc_id == patient_orthanc_id,
            Dataset_Studies.study_orthanc_id == study_orthanc_id,
            Dataset_Studies.dataset_id == dataset_id,
        )
    ).first()
    if study_pair is None:
        abort(404, description="Dataset-patient and study do not match")

    series = Series.query.filter_by(series_orthanc_id=series_orthanc_id).first()
    if series is None:
        create_series(orthanc_data)
    else:
        series.valid = True
        db.session.commit()

    new_series_pair = Dataset_Series(
        DP_S_pair_id=study_pair.DP_S_pair_id,
        patient_orthanc_id=patient_orthanc_id,
        study_orthanc_id=study_orthanc_id,
        series_orthanc_id=series_orthanc_id,
        dataset_id=dataset_id,
    )
    db.session.add(new_series_pair)
    db.session.commit()


def create_series(orthanc_data):
    series_orthanc_id = orthanc_data["ParentSeries"]
    series_info = get_series_info(series_orthanc_id)
    main_dicom_tags = series_info.get("MainDicomTags", {})

    def safe_int(value):
        try:
            return int(value) if value else None
        except ValueError:
            return None

    new_series = Series(
        series_orthanc_id=series_orthanc_id,
        series_instance_uid=main_dicom_tags.get("SeriesInstanceUID", ""),
        series_date=main_dicom_tags.get("SeriesDate", ""),
        series_time=main_dicom_tags.get("SeriesTime", ""),
        modality=main_dicom_tags.get("Modality", ""),
        manufacturer=main_dicom_tags.get("Manufacturer", ""),
        station_name=main_dicom_tags.get("StationName", ""),
        series_description=main_dicom_tags.get("SeriesDescription", ""),
        body_part_examined=main_dicom_tags.get("BodyPartExamined", ""),
        sequence_name=main_dicom_tags.get("SequenceName", ""),
        protocol_name=main_dicom_tags.get("ProtocolName", ""),
        series_number=safe_int(main_dicom_tags.get("SeriesNumber")),
        cardiac_number_of_images=safe_int(main_dicom_tags.get("CardiacNumberOfImages")),
        images_in_acquisition=safe_int(main_dicom_tags.get("ImagesInAcquisition")),
        number_of_temporal_positions=safe_int(main_dicom_tags.get("NumberOfTemporalPositions")),
        number_of_slices=safe_int(main_dicom_tags.get("NumberOfSlices")),
        number_of_time_slices=safe_int(main_dicom_tags.get("NumberOfTimeSlices")),
        image_orientation_patient=main_dicom_tags.get("ImageOrientationPatient", ""),
        series_type=main_dicom_tags.get("SeriesType", ""),
        operators_name=main_dicom_tags.get("OperatorsName", ""),
        performed_procedure_step_description=main_dicom_tags.get("PerformedProcedureStepDescription", ""),
        acquisition_device_processing_description=main_dicom_tags.get("AcquisitionDeviceProcessingDescription", ""),
        contrast_bolus_agent=main_dicom_tags.get("ContrastBolusAgent", ""),
    )
    db.session.add(new_series)
    db.session.commit()


def create_instance_pair(orthanc_data):
    series_orthanc_id = orthanc_data["ParentSeries"]
    instance_orthanc_id = orthanc_data["ID"]

    new_instance_pair = Dataset_Instances(
        series_orthanc_id=series_orthanc_id,
        instance_orthanc_id=instance_orthanc_id,
        status=0,
    )
    db.session.add(new_instance_pair)
    db.session.commit()


def update_database_records(orthanc_data, dataset_id):
    """Update database records"""
    try:
        patient_pair = Dataset_Patients.query.filter(
            and_(
                Dataset_Patients.patient_orthanc_id == orthanc_data["ParentPatient"],
                Dataset_Patients.dataset_id == dataset_id,
            )
        ).first()
        
        if patient_pair is None:
            create_patient_pair(orthanc_data, dataset_id)
        else:
            patient_pair.valid = True
            db.session.commit()
        
        study_pair = Dataset_Studies.query.filter(
            and_(
                Dataset_Studies.patient_orthanc_id == orthanc_data["ParentPatient"],
                Dataset_Studies.study_orthanc_id == orthanc_data["ParentStudy"],
                Dataset_Studies.dataset_id == dataset_id,
            )
        ).first()
        
        if study_pair is None:
            create_study_pair(orthanc_data, dataset_id)
        else:
            study_pair.valid = True
            db.session.commit()
        
        series_pair = Dataset_Series.query.filter(
            and_(
                Dataset_Series.patient_orthanc_id == orthanc_data["ParentPatient"],
                Dataset_Series.study_orthanc_id == orthanc_data["ParentStudy"],
                Dataset_Series.series_orthanc_id == orthanc_data["ParentSeries"],
                Dataset_Series.dataset_id == dataset_id,
            )
        ).first()
        
        if series_pair is None:
            create_series_pair(orthanc_data, dataset_id)
        else:
            series_pair.valid = True
            db.session.commit()
        
        instance_pair = Dataset_Instances.query.filter(
            and_(
                Dataset_Instances.series_orthanc_id == orthanc_data["ParentSeries"],
                Dataset_Instances.instance_orthanc_id == orthanc_data["ID"]
            )
        ).first()
        
        if instance_pair is None:
            create_instance_pair(orthanc_data)
        else:
            instance_pair.status = 0
            db.session.commit()
            
        return True, None
    except Exception as e:
        return False, f"Database error: {str(e)}"