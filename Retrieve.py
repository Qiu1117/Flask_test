from flask import (
    jsonify,
    request,
    Blueprint,
)
from middleware import token_required, permission_check
from flask import g
from db_models import (
    Dataset_Patients,
    Dataset_Studies,
    Dataset_Series,
    Dataset_Instances,
)
import requests
import config


retrieve = Blueprint("retrieve", __name__)


def orthanc_request(method, endpoint, **kwargs):
    url = f"{config.ORTHANC_URL}/{endpoint.lstrip('/')}"
    auth = (config.ORTHANC_USERNAME, config.ORTHANC_PASSWORD)
    
    if 'auth' not in kwargs:
        kwargs['auth'] = auth
        
    return requests.request(method, url, **kwargs)


# ------------------------------------------ Notification --------------------------------------
@retrieve.route("/retrieve_data", methods=["POST"])
@token_required()
def retrieve_data():
    content = request.get_json()

    orthanc_find_url = "tools/find"

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
        response = orthanc_request("POST", orthanc_find_url, json=orthanc_content)
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
                    "status": "valid",
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
                    "status": "valid",
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
                    "status": "valid",
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
                    "status": "valid",
                }
            )

    if not db_results:
        db_results.append({"status": "Data is invalid."})

    return jsonify(db_results), 200
