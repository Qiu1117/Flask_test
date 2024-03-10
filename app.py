from flask import Flask, request, jsonify, send_file, session
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import json
import pydicom
import os
import requests
from MPF_Cal import mpf
from User_DB import user, verify_token


app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
jwt = JWTManager(app)
app.secret_key = "cuhkdiir"

UPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

MPFUPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads\mpf"
app.config["MPFUPLOAD_FOLDER"] = MPFUPLOAD_FOLDER

orthanc_url = "http://127.0.0.1:8042"


# ---------------------------------------数据管理--------------------------
@app.route("/upload", methods=["POST"])
# @verify_token()
def upload():
    files = []
    for key in request.files.keys():
        if key.startswith("file"):
            files.extend(request.files.getlist(key))

    if len(files) == 0:
        return "No files uploaded."

    file_paths = []
    for file in files:
        if file.filename == "":
            return "Empty filename."
        file_name = file.filename.replace("/", "_")
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)
        file.save(file_path)
        file_paths.append(file_path)

    # --orthanc--
    for file_path in file_paths:
        upload_url = f"{orthanc_url}/instances"  # Orthanc的URL
        with open(file_path, "rb") as f:
            orthanc_files = {"file": (file_path, f, "application/dicom")}
            response = requests.post(upload_url, files=orthanc_files)
            print(response)
    # --orthanc--

    return "Success upload"


@app.route("/search_AllPatient", methods=["GET"])
# @verify_token()
def search_AllPatient():
    Patient_url = f"{orthanc_url}/patients?expand"
    response = requests.get(Patient_url)
    patients_list = []

    if response.status_code == 200:
        patients = response.json()
        for i in range(len(patients)):
            ID = patients[i]["ID"]
            patient_Name = patients[i]["MainDicomTags"]["PatientName"]
            patient_ID = patients[i]["MainDicomTags"]["PatientID"]
            patient_Studies = patients[i]["Studies"]

            patient_dict = {
                "ID": ID,
                "PatientName": patient_Name,
                "PatientID": patient_ID,
                "Studies": patient_Studies,
            }
            patients_list.append(patient_dict)

    return jsonify(patients_list)


@app.route("/search_AllStudy", methods=["GET"])
# @verify_token()
def search_AllStudy():
    Study_url = f"{orthanc_url}/studies?expand"

    response = requests.get(Study_url)
    studies_list = []

    if response.status_code == 200:
        studies = response.json()
        for i in range(len(studies)):
            study_Description = studies[i]["MainDicomTags"]["StudyDescription"]
            study_ID = studies[i]["ID"]
            study_Date = studies[i]["MainDicomTags"]["StudyDate"]
            study_InstanceUID = studies[i]["MainDicomTags"]["StudyInstanceUID"]
            study_Accessnumber = studies[i]["MainDicomTags"]["AccessionNumber"]
            study_Series = studies[i]["Series"]

            study_dict = {
                "study_Description": study_Description,
                "study_Date": study_Date,
                "study_ID": study_ID,
                "study_InstanceUID": study_InstanceUID,
                "study_Accessnumber": study_Accessnumber,
                "study_Series": study_Series,
            }
            studies_list.append(study_dict)

    return jsonify(studies_list)


@app.route("/search_Study", methods=["GET"])
# @verify_token()
def search_Study():
    patient_id = request.args.get("PatientID")

    study_dict = {}
    study_url = f"{orthanc_url}/patients/{patient_id}/studies?full"
    study_response = requests.get(study_url)
    studies_list = []
    if study_response.status_code == 200:
        study_info = study_response.json()
        for i in range(len(study_info)):
            study_ID = study_info[i]["ID"]
            study_Description = study_info[i]["MainDicomTags"]["0008,1030"]["Value"]
            study_Date = study_info[i]["MainDicomTags"]["0008,0020"]["Value"]
            study_UID = study_info[i]["MainDicomTags"]["0020,000d"]["Value"]
            study_Accessnumber = study_info[i]["MainDicomTags"]["0008,0050"]["Value"]
            study_Series = study_info[i]["Series"]

            study_dict = {
                "ID": study_ID,
                "study_Description": study_Description,
                "study_Date": study_Date,
                "study_UID": study_UID,
                "study_Accessnumber": study_Accessnumber,
                "study_Series": study_Series,
            }
            studies_list.append(study_dict)

    return jsonify(studies_list)


@app.route("/search_Series", methods=["GET"])
# @verify_token()
def search_Series():
    study_id = request.args.get("StudyID")

    series_dict = {}
    serie_url = f"{orthanc_url}/studies/{study_id}/series?full"
    series_response = requests.get(serie_url)
    series_list = []
    if series_response.status_code == 200:
        series_info = series_response.json()
        for i in range(len(series_info)):
            series_ID = series_info[i]["ID"]
            series_Modality = series_info[i]["MainDicomTags"]["0008,0060"]["Value"]
            series_SeriesInstanceUID = series_info[i]["MainDicomTags"]["0020,000e"][
                "Value"
            ]
            series_SeriesNumber = series_info[i]["MainDicomTags"]["0008,0031"]["Value"]
            series_ProtocolName = series_info[i]["MainDicomTags"]["0018,1030"]["Value"]
            series_Instances = series_info[i]["Instances"]

            series_dict = {
                "ID": series_ID,
                "Modality": series_Modality,
                "SeriesNumber": series_SeriesNumber,
                "SeriesInstanceUID": series_SeriesInstanceUID,
                "ProtocolName": series_ProtocolName,
                "Instances": series_Instances,
            }
            series_list.append(series_dict)

    return jsonify(series_list)


@app.route("/search_Instance", methods=["GET"])
# @verify_token()
def search_Instance():
    series_ID = request.args.get("SeriesID")

    Instances_url = f"{orthanc_url}/series/{series_ID}/instances?full"

    instance_response = requests.get(Instances_url)
    instance_list = []
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        for i in range(len(instance_info)):
            instance_ID = instance_info[i]["ID"]
            instance_SOPInstanceUID = instance_info[i]["MainDicomTags"]["0008,0018"][
                "Value"
            ]
            instance_dict = {
                "ID": instance_ID,
                "SOPInstanceUID": instance_SOPInstanceUID,
            }
            instance_list.append(instance_dict)

    return jsonify(instance_list)


@app.route("/get_Instance", methods=["GET"])
# @verify_token()
def get_Instance():
    Instances_url = f"{orthanc_url}/instances"
    Instances_id = request.args.get("instance_ID")
    Instance_url = f"{Instances_url}/{Instances_id}"
    download_url = f"{Instance_url}/file"
    response = requests.get(download_url)

    return response.content


@app.route("/delete-files", methods=["DELETE"])
# @verify_token()
def deletefiles():
    delete_dict = {
        "Patient": "patients",
        "Series": "series",
        "Study": "studies",
        "Instances": "instances",
    }
    fileClass_list = request.args.get("file_Class")
    fileClass_list = json.loads(fileClass_list)
    print(fileClass_list)
    fileID_list = request.args.get("file_ID")
    fileID_list = json.loads(fileID_list)

    for i in range(len(fileID_list)):
        fileID = fileID_list[i]
        fileClass = delete_dict[fileClass_list[i]]
        deleteUrl = f"{orthanc_url}/{fileClass}/{fileID}"

        delete_response = requests.delete(deleteUrl)
        if delete_response.status_code != 200:
            return jsonify("Fail to delete selected files!")

    return jsonify("Success delete selected files!")


@app.route("/proxy/<path:url_path>", methods=["GET"])
# @verify_token()
def get_file(url_path):
    print(url_path)
    orthanc_backend = "http://localhost:8042/dicom-web"
    file_url = f"{orthanc_backend}/{url_path}"
    response = requests.get(file_url)

    return response.content


# ---------------------------------------数据管理--------------------------

# ---------------------------------------用户和注册--------------------------
app.register_blueprint(user)


# ---------------------------------------mpf--------------------------------
app.register_blueprint(mpf)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
