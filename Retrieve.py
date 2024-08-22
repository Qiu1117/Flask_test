from flask import (
    Flask,
    jsonify,
    request,
    Response,
    stream_with_context,
    Blueprint,
    abort,
)
import time
import sqlite3
from middleware import token_required, permission_check
import json
import shortuuid
from flask import g
from flask_cors import CORS
from collections import defaultdict
from db_models import (
    db,
    Account,
    Group,
    Acc_Group,
    Dataset_Group,
    Dataset,
    Patient,
    Dataset_Patients,
    Dataset_Studies,
    Dataset_Series,
    Dataset_Instances,
)
from sqlalchemy.types import Unicode
from sqlalchemy import update, text, func, and_, or_
import sqlalchemy
import requests
import pydicom


retrieve = Blueprint("retrieve", __name__)
orthanc_url = "http://127.0.0.1:8042"


# ------------------------------------------ Notification --------------------------------------
@retrieve.route("/retrieve_data", methods=["POST"])
@token_required()
def retrieve_data():
    content = request.get_json()

    orthanc_find_url = f"{orthanc_url}/tools/find"

    orthanc_content = {
        "Level": content["level"],
        "Query": {},
        "Expand": True,
        "Limit": 100,  # 添加默认限制
        "RequestedTags": ["PatientName", "PatientID", "StudyDescription", "StudyDate"],
    }

    for tag_info in content["tags"]:
        if tag_info["tag"] and tag_info["value"]:
            orthanc_content["Query"][tag_info["tag"]] = tag_info["value"]

    if "label" in content and content["label"]:
        orthanc_content["Labels"] = [content["label"]]


    try:
        response = requests.post(orthanc_find_url, json=orthanc_content)
        response.raise_for_status()

        return jsonify(response.json()), response.status_code

    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


@retrieve.route("/retrieve_datasetinfo", methods=["POST"])
@token_required()
def retrieve_datasetinfo():
    content = request.get_json()

    level = content.get("level")
    orthanc_id = content.get("ID")

    db_results = []

    if level == "Patient":
        db_results_set = Dataset_Patients.query.filter_by(
            patient_orthanc_id=orthanc_id
        ).all()
        for db_result in db_results_set:
            db_results.append(
                {
                    "PatientOrthancID": db_result.patient_orthanc_id,
                    "Dataset_id": db_result.dataset_id,
                }
            )
    elif level == "Study":
        db_results_set = Dataset_Studies.query.filter_by(
            study_orthanc_id=orthanc_id
        ).all()
        for db_result in db_results_set:
            db_results.append(
                {
                    "StudyOrthancID": db_result.study_orthanc_id,
                    "PatientOrthancID": db_result.patient_orthanc_id,
                    "DatasetID": db_result.dataset_id,
                }
            )
    elif level == "Series":
        db_results_set = Dataset_Series.query.filter_by(
            series_orthanc_id=orthanc_id
        ).all()
        for db_result in db_results_set:
            db_results.append(
                {
                    "SeriesOrthancID": db_result.series_orthanc_id,
                    "StudyOrthancID": db_result.study_orthanc_id,
                    "PatientOrthancID": db_result.patient_orthanc_id,
                    "DatasetID": db_result.dataset_id,
                }
            )
    elif level == "Instance":
        db_results_set = Dataset_Instances.query.filter_by(
            instance_orthanc_id=orthanc_id
        ).all()
        for db_result in db_results_set:
            db_results.append(
                {
                    "InstanceOrthancID": db_result.instance_orthanc_id,
                    "SeriesOrthancID": db_result.series_orthanc_id,
                    "Status": db_result.status,
                }
            )

    return jsonify(db_results), 200
