from flask import jsonify, request, abort
from middleware import token_required
from sqlalchemy import and_
from db_models import (
    Dataset_Patients, Dataset_Studies, Dataset_Series, 
    Dataset_Instances, Patient
)
from orthanc_utils import orthanc_request


def _get_study_info(study_orthanc_id):
    study_url = f"studies/{study_orthanc_id}?=short"
    
    study_dict = {
        "StudyDescription": "",
        "StudyDate": "",
        "study_orthanc_id": study_orthanc_id,
        "StudyInstanceUID": "",
        "AccessionNumber": "",
    }
    
    response = orthanc_request("GET", study_url)

    if response.status_code == 200:
        studies_info = response.json()
        main_dicom_tags = studies_info.get("MainDicomTags", {})

        study_dict = {
            "StudyDescription": main_dicom_tags.get("StudyDescription", ""),
            "StudyDate": main_dicom_tags.get("StudyDate", ""),
            "study_orthanc_id": study_orthanc_id,
            "StudyInstanceUID": main_dicom_tags.get("StudyInstanceUID", ""),
            "AccessionNumber": main_dicom_tags.get("AccessionNumber", ""),
        }
    
    return study_dict

def _get_series_info(series_orthanc_id):
    serie_url = f"series/{series_orthanc_id}?=short"
    
    series_dict = {
        "series_orthanc_id": series_orthanc_id,
        "Modality": "",
        "SeriesNumber": "",
        "SeriesInstanceUID": "",
        "ProtocolName": ""
    }
    
    series_response = orthanc_request("GET", serie_url)
    if series_response.status_code == 200:
        series_info = series_response.json()
        main_dicom_tags = series_info.get("MainDicomTags", {})

        series_dict = {
            "series_orthanc_id": series_orthanc_id,
            "Modality": main_dicom_tags.get("Modality", ""),
            "SeriesNumber": main_dicom_tags.get("SeriesNumber", ""),
            "SeriesInstanceUID": main_dicom_tags.get("SeriesInstanceUID", ""),
            "ProtocolName": main_dicom_tags.get("ProtocolName", ""),
        }

    return series_dict

def _get_instance_info(instance_orthanc_id):
    instance_url = f"instances/{instance_orthanc_id}?=short"
    
    instance_dict = {
        "instance_orthanc_id": instance_orthanc_id,
        "SOPInstanceUID": ""
    }
    
    instance_response = orthanc_request("GET", instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        instance_dict = {
            "instance_orthanc_id": instance_orthanc_id,
            "SOPInstanceUID": instance_info["MainDicomTags"].get("SOPInstanceUID", ""),
        }

    return instance_dict

def _get_study_taginfo(study_orthanc_id):
    study_url = f"studies/{study_orthanc_id}?=full"
    main_dicom_tags = {}
    
    response = orthanc_request("GET", study_url)
    if response.status_code == 200:
        studies_info = response.json()
        main_dicom_tags = studies_info.get("MainDicomTags", {})

    return main_dicom_tags

def _get_series_taginfo(series_orthanc_id):
    serie_url = f"series/{series_orthanc_id}?=full"
    main_dicom_tags = {}
    
    series_response = orthanc_request("GET", serie_url)
    if series_response.status_code == 200:
        series_info = series_response.json()
        main_dicom_tags = series_info.get("MainDicomTags", {})

    return main_dicom_tags

def _get_instance_taginfo(instance_orthanc_id):
    instance_url = f"instances/{instance_orthanc_id}?=full"
    main_dicom_tags = {}
    
    instance_response = orthanc_request("GET", instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        main_dicom_tags = instance_info.get("MainDicomTags", {})

    return main_dicom_tags


def search_Patient():  # 添加这个函数
    dataset_id = request.args['dataset_id']

    dataset_patients = Dataset_Patients.query.filter(
        Dataset_Patients.dataset_id == dataset_id
    ).all()
    if not dataset_patients: 
        abort(404, description="No patient was found")

    patient_list = []
    for patient in dataset_patients:
        if patient.valid:
            patient_list.append(patient.patient_orthanc_id)

    patients = Patient.query.filter(Patient.patient_orthanc_id.in_(patient_list)).all()
    patient_dict = []
    for patient in patients:
        patient_dict.append({
            "patient_orthanc_id": patient.patient_orthanc_id,
            "PatientName": patient.patient_name,
            "PatientID": patient.patient_id,
            "PatientBirthDate": patient.patient_birthdate,
            "PatientSex": patient.patient_sex,
        })
    return jsonify(patient_dict)

def search_study():
    dataset_id = request.args['dataset_id']
    patient_id = request.args["patient_id"]

    study_pair = Dataset_Studies.query.filter(
        and_(
            Dataset_Studies.patient_orthanc_id == patient_id,
            Dataset_Studies.dataset_id == dataset_id,
        )
    ).all()
    if not study_pair: 
        abort(404, description="No study was found")

    study_dict = []
    for study in study_pair:
        if study.valid:
            info = _get_study_info(study.study_orthanc_id)
            study_dict.append(info)

    return jsonify(study_dict)

def search_series():
    dataset_id = request.args["dataset_id"]
    patient_id = request.args["patient_id"]
    study_id = request.args["study_id"]

    series_pair = Dataset_Series.query.filter(
        and_(
            Dataset_Series.patient_orthanc_id == patient_id,
            Dataset_Series.study_orthanc_id == study_id,
            Dataset_Series.dataset_id == dataset_id,
        )
    ).all()
    if not series_pair:
        abort(404, description="No series was found")

    series_dict = []
    for series in series_pair:
        if series.valid:
            info = _get_series_info(series.series_orthanc_id)
            series_dict.append(info)
    return jsonify(series_dict)

def search_instances():
    series_orthanc_id = request.args['series_orthanc_id']

    instance_pair = Dataset_Instances.query.filter(
        Dataset_Instances.series_orthanc_id == series_orthanc_id
    ).all()
    if not instance_pair:
        abort(404, description="No instance was found")

    instance_dict = []
    for instance in instance_pair:
        if instance.status == 0:
            info = _get_instance_info(instance.instance_orthanc_id)
            instance_dict.append(info)

    return jsonify(instance_dict)

def get_maintag_info():
    orthanc_id = request.args["id"]
    info_class = request.args["class"]
    
    result_dict = None
    if info_class == "Study":
        result_dict = _get_study_taginfo(orthanc_id)
    elif info_class == "Series":
        result_dict = _get_series_taginfo(orthanc_id)
    elif info_class == "Instances":
        result_dict = _get_instance_taginfo(orthanc_id)
    else:
        abort(400, description="Invalid 'class' parameter")

    if result_dict is None:
        abort(404, description=f"No data found for {info_class} with ID {orthanc_id}")

    return jsonify(result_dict)

def get_study_info(study_orthanc_id):
    study_url = f"studies/{study_orthanc_id}?=short"
    
    study_dict = {
        "StudyDescription": "",
        "StudyDate": "",
        "study_orthanc_id": study_orthanc_id,
        "StudyInstanceUID": "",
        "AccessionNumber": "",
    }
    
    response = orthanc_request("GET", study_url)

    if response.status_code == 200:
        studies_info = response.json()
        main_dicom_tags = studies_info.get("MainDicomTags", {})

        study_dict = {
            "StudyDescription": main_dicom_tags.get("StudyDescription", ""),
            "StudyDate": main_dicom_tags.get("StudyDate", ""),
            "study_orthanc_id": study_orthanc_id,
            "StudyInstanceUID": main_dicom_tags.get("StudyInstanceUID", ""),
            "AccessionNumber": main_dicom_tags.get("AccessionNumber", ""),
        }
    
    return study_dict


def get_series_info(series_orthanc_id):
    serie_url = f"series/{series_orthanc_id}?=short"
    
    series_dict = {
        "series_orthanc_id": series_orthanc_id,
        "Modality": "",
        "SeriesNumber": "",
        "SeriesInstanceUID": "",
        "ProtocolName": ""
    }
    
    series_response = orthanc_request("GET", serie_url)
    if series_response.status_code == 200:
        series_info = series_response.json()
        main_dicom_tags = series_info.get("MainDicomTags", {})

        series_dict = {
            "series_orthanc_id": series_orthanc_id,
            "Modality": main_dicom_tags.get("Modality", ""),
            "SeriesNumber": main_dicom_tags.get("SeriesNumber", ""),
            "SeriesInstanceUID": main_dicom_tags.get("SeriesInstanceUID", ""),
            "ProtocolName": main_dicom_tags.get("ProtocolName", ""),
        }

    return series_dict


def get_instance_info(instance_orthanc_id):
    instance_url = f"instances/{instance_orthanc_id}?=short"
    
    instance_dict = {
        "instance_orthanc_id": instance_orthanc_id,
        "SOPInstanceUID": ""
    }
    
    instance_response = orthanc_request("GET", instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        instance_dict = {
            "instance_orthanc_id": instance_orthanc_id,
            "SOPInstanceUID": instance_info["MainDicomTags"].get("SOPInstanceUID", ""),
        }

    return instance_dict


def get_study_taginfo(study_orthanc_id):
    study_url = f"studies/{study_orthanc_id}?=full"
    main_dicom_tags = {}
    
    response = orthanc_request("GET", study_url)
    if response.status_code == 200:
        studies_info = response.json()
        main_dicom_tags = studies_info.get("MainDicomTags", {})

    return main_dicom_tags


def get_series_taginfo(series_orthanc_id):
    serie_url = f"series/{series_orthanc_id}?=full"
    main_dicom_tags = {}
    
    series_response = orthanc_request("GET", serie_url)
    if series_response.status_code == 200:
        series_info = series_response.json()
        main_dicom_tags = series_info.get("MainDicomTags", {})

    return main_dicom_tags


def get_instance_taginfo(instance_orthanc_id):
    instance_url = f"instances/{instance_orthanc_id}?=full"
    main_dicom_tags = {}
    
    instance_response = orthanc_request("GET", instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        main_dicom_tags = instance_info.get("MainDicomTags", {})

    return main_dicom_tags