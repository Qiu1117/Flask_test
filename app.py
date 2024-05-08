from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from flask import g
import json
import os
import requests
from MPF_Cal import mpf
from User_DB import user, verify_token
from flask import current_app
from CRUD import crud
from db_models import db
from config import ProductionConfig
from flask_migrate import Migrate
from db_models import Account, Dataset, Group


app = Flask(__name__)
app.config.from_object(ProductionConfig)
CORS(app)
db.init_app(app)  # init database
migrate = Migrate(app, db)

with app.app_context():
    db.create_all()

# app.secret_key = "cuhkdiir"

UPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

MPFUPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads\mpf"
app.config["MPFUPLOAD_FOLDER"] = MPFUPLOAD_FOLDER

orthanc_url = "http://127.0.0.1:8042"


# ---------------------------------------数据管理--------------------------

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
app.register_blueprint(crud)

# ---------------------------------------用户和注册--------------------------
app.register_blueprint(user)


# ---------------------------------------mpf--------------------------------
app.register_blueprint(mpf)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
