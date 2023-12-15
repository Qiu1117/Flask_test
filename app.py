from flask import Flask, request, jsonify, send_file, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    decode_token,
    jwt_required,
    get_jwt_identity,
)
from jwt.exceptions import ExpiredSignatureError
from flask_cors import CORS
from pymongo import MongoClient
import pydicom
from bson.objectid import ObjectId
import os
import time
import json
import requests
from run import QMR_main

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
jwt = JWTManager(app)
app.secret_key = "cuhkdiir"
client = MongoClient("mongodb://localhost:27017")
db = client["Dicom"]

UPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

MPFUPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads\mpf"
app.config["MPFUPLOAD_FOLDER"] = MPFUPLOAD_FOLDER

orthanc_url = "http://localhost:8042"


# ---------------------------------------数据管理--------------------------
@app.route("/upload", methods=["POST"])
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

        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)
        file_paths.append(file_path)

    # --orthanc--
    for file_path in file_paths:
        orthanc_url = "http://localhost:8042/instances"  # Orthanc的URL
        with open(file_path, "rb") as f:
            orthanc_files = {"file": (file_path, f, "application/dicom")}
            response = requests.post(orthanc_url, files=orthanc_files)
            print(response)
    # --orthanc--

    return "Success upload"


@app.route("/search_by_ip", methods=["GET"])
def search_data_by_ip():
    orthanc_url = "http://localhost:8042"
    instances_url = f"{orthanc_url}/instances"
    response = requests.get(instances_url)

    if response.status_code == 200:
        instances = response.json()
        for instance_id in instances:
            instance_url = f"{instances_url}/{instance_id}"
            instance_response = requests.get(instance_url)
            if instance_response.status_code == 200:
                instance_info = instance_response.json()

    orthanc_url = "http://localhost:8042//instances/25cb52ed-0f7f5402-ff7bb7e8-de7de598-64e4d2fb/file"
    response = requests.get(orthanc_url)
    file_path = r"C:\Users\Qiuyi\Desktop\uploads\orthanc\test.dcm"
    with open(file_path, "wb") as file:
        file.write(response.content)

    return


@app.route("/search_AllPatient", methods=["GET"])
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
            patient_Birthday = patients[i]["MainDicomTags"]["PatientBirthDate"]
            patient_Studies = patients[i]["Studies"]

            patient_dict = {
                "ID": ID,
                "PatientName": patient_Name,
                "PatientID": patient_ID,
                "PatientBirthday": patient_Birthday,
                "Studies": patient_Studies,
            }
            patients_list.append(patient_dict)

    return jsonify(patients_list)


@app.route("/search_AllStudy", methods=["GET"])
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
            study_InstanceUID = study_info[i]["MainDicomTags"]["0020,000d"]["Value"]
            study_Accessnumber = study_info[i]["MainDicomTags"]["0008,0050"]["Value"]
            study_Series = study_info[i]["Series"]

            study_dict = {
                "ID": study_ID,
                "study_Description": study_Description,
                "study_Date": study_Date,
                "study_InstanceUID": study_InstanceUID,
                "study_Accessnumber": study_Accessnumber,
                "study_Series": study_Series,
            }
            studies_list.append(study_dict)

    return jsonify(studies_list)


@app.route("/search_Series", methods=["GET"])
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
            series_Description = series_info[i]["MainDicomTags"]["0040,0254"]["Value"]
            series_Modality = series_info[i]["MainDicomTags"]["0008,0060"]["Value"]
            series_SeriesInstanceUID = series_info[i]["MainDicomTags"]["0020,000e"][
                "Value"
            ]
            series_SeriesNumber = series_info[i]["MainDicomTags"]["0008,0031"]["Value"]
            series_ProtocolName = series_info[i]["MainDicomTags"]["0018,1030"]["Value"]
            series_Instances = series_info[i]["Instances"]

            series_dict = {
                "ID": series_ID,
                "Description": series_Description,
                "Modality": series_Modality,
                "SeriesNumber": series_SeriesNumber,
                "SeriesInstanceUID": series_SeriesInstanceUID,
                "ProtocolName": series_ProtocolName,
                "Instances": series_Instances,
            }
            series_list.append(series_dict)

    return jsonify(series_list)


@app.route("/search_Instance", methods=["GET"])
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
def get_Instance():
    Instances_url = f"{orthanc_url}/instances"
    Instances_id = request.args.get("instance_ID")

    Instance_url = f"{Instances_url}/{Instances_id}"
    instance_response = requests.get(Instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        instance_ID = instance_info["ID"]
        instance_ParentSeries = instance_info["ParentSeries"]

        download_url = f"{Instance_url}/file"
        response = requests.get(download_url)
        folder_path = f"C:\\Users\\Qiuyi\\Desktop\\uploads\\{instance_ParentSeries}"
        os.makedirs(folder_path, exist_ok=True)
        file_path = f"C:\\Users\\Qiuyi\\Desktop\\uploads\\{instance_ParentSeries}\\{instance_ID}.dcm"
        with open(file_path, "wb") as file:
            file.write(response.content)

        return send_file(file_path, mimetype="application/dicom")

    return "File does not exist!"


@app.route("/delete-files", methods=["POST"])
def deletefiles():
    Instances_id = request.args.get("instance_ID")
    Instances_url = f"{orthanc_url}/instances"
    Instances_id = request.args.get("instance_ID")

    instance_dict = {}
    Instance_url = f"{Instances_url}/{Instances_id}"
    instance_response = requests.get(Instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        instance_ID = instance_info["ID"]
        instance_SOPInstanceUID = instance_info["MainDicomTags"]["SOPInstanceUID"]

        instance_dict = {"ID": instance_ID, "SOPInstanceUID": instance_SOPInstanceUID}

    return jsonify("Success delete selected files!")


@app.route("/get_file", methods=["GET"])
def get_file():
    file_address = request.args.get("fileAddress")
    file_path = file_address
    return send_file(file_path, mimetype="application/dicom")


# ---------------------------------------数据管理--------------------------

# ---------------------------------------用户和注册--------------------------
users_collection = db["users"]


@app.route("/register", methods=["POST"])
def register():
    username = request.json["username"]
    password = request.json["password"]

    # 检查用户名是否已存在
    existing_user = users_collection.find_one({"username": username})
    if existing_user:
        return jsonify({"message": "Username already exists"}), 400

    # 创建新用户
    hashed_password = generate_password_hash(password)
    user_id = users_collection.insert_one(
        {"username": username, "password": hashed_password}
    ).inserted_id

    return jsonify({"user_id": str(user_id)}), 201


# 用户登录接口
@app.route("/login", methods=["POST"])
def login():
    username = request.json["username"]
    password = request.json["password"]

    # 根据用户名查找用户
    user = users_collection.find_one({"username": username})

    if user and check_password_hash(user["password"], password):
        # 生成访问令牌
        access_token = create_access_token(identity=str(user["_id"]))
        session["username"] = username
        return jsonify({"access_token": access_token})

    return jsonify({"message": "Invalid username or password"}), 401


@app.route("/verify-token", methods=["POST"])
def verify_token():
    token = request.json.get("token")
    try:
        decoded_token = decode_token(token)
        user_id = decoded_token["sub"]
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if user:
            return jsonify({"valid": True, "sub": user_id})

    except ExpiredSignatureError:
        return jsonify({"valid": False, "message": "Token has expired"})
    except Exception as e:
        return jsonify({"valid": False, "message": "Invalid token"})


@app.route("/logout", methods=["GET"])
def logout():
    session.pop("username", None)
    return jsonify({"valid": True, "message": "Logged out successfully"})


# ---------------------------------------用户和注册--------------------------


# ---------------------------------------mpf--------------------------------
@app.route("/mpf", methods=["POST"])
def rmpfsl_cal():
    files = []
    realctr = []
    ictr = []
    tsl = float(request.args.get("tsl"))
    for key in request.files.keys():
        if key.startswith("file"):
            files.extend(request.files.getlist(key))

    if len(files) == 0:
        return "No files uploaded."

    # client_ip = request.remote_addr
    # collection_name = f"collection_{client_ip.replace('.', '_')}"
    # if db.get_collection(collection_name) is not None:
    #     collection = db[collection_name]
    # else:
    #     collection = db.create_collection(collection_name)
    for file in files:
        if file.filename == "":
            return "Empty filename."

        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)

        ds = pydicom.dcmread(file_path)
        sop_instance_uid = ds.SOPInstanceUID
        # existing_doc = collection.find_one({"sopInstanceUID": sop_instance_uid})

        # if existing_doc is None:
        #     patient_name = ds.PatientName
        #     pixel_size = {"width": ds.Columns, "height": ds.Rows}
        #     pixel_data_type = ds.pixel_array.dtype.name

        #     dicom_metadata = {
        #         "fileName": file.filename,
        #         "sopInstanceUID": sop_instance_uid,
        #         "patientName": str(patient_name),
        #         "pixelSize": pixel_size,
        #         "pixelDataType": pixel_data_type,
        #         "address": file_path,
        #         "clientIP": client_ip,
        #     }
        #     collection.insert_one(dicom_metadata)
        if ds.ImageType[3] in ["R", "r"]:
            realctr.append(file_path)
        elif ds.ImageType[3] in ["I", "i"]:
            ictr.append(file_path)

    time.sleep(1)
    if len(realctr) == len(ictr):
        QMR_main(realctr, ictr, tsl)
    else:
        return "real and imaginer does not match !"

    image_path = r"C:\Users\Qiuyi\Desktop\uploads\mpf\Mpf_output.dcm"
    return send_file(image_path, mimetype="application/dicom")
    # return


# ---------------------------------------mpf--------------------------------


if __name__ == "__main__":
    app.run(host="0.0.0.0")
