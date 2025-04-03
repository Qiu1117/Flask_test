from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from flask import g
import os
import requests
from MPF_Cal import mpf
from User_DB import user, verify_token
from flask import current_app
from CRUD import crud
from Retrieve import retrieve
from Dashboard import dashboard
from db_models import db
from config import ProductionConfig
from flask_migrate import Migrate
from db_models import Account, Dataset, Group
from Pipeline import pipeline_bp



app = Flask(__name__)
app.config.from_object(ProductionConfig)
CORS(app)
db.init_app(app) 
migrate = Migrate(app, db)

with app.app_context():
    db.create_all()

# app.secret_key = "cuhkdiir"

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
MPFUPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "mpf")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MPFUPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MPFUPLOAD_FOLDER"] = MPFUPLOAD_FOLDER

orthanc_url = "http://127.0.0.1:8042"
orthanc_username = "orthanc"
orthanc_password = "orthanc"

def orthanc_request(method, endpoint, **kwargs):
    url = f"{orthanc_url}/{endpoint.lstrip('/')}"
    auth = (orthanc_username, orthanc_password)
    
    # 如果没有指定auth参数，添加默认认证
    if 'auth' not in kwargs:
        kwargs['auth'] = auth
        
    return requests.request(method, url, **kwargs)


# ---------------------------------------数据管理--------------------------


@app.route("/proxy/<path:url_path>", methods=["GET"])
# @verify_token()
def get_file(url_path):
    print(url_path)
    orthanc_backend = "http://localhost:8042/dicom-web"
    file_url = f"{orthanc_backend}/{url_path}"
    
    # 使用认证信息请求Orthanc
    response = requests.get(
        file_url,
        auth=(orthanc_username, orthanc_password)
    )

    return response.content


# ---------------------------------------数据管理--------------------------
app.register_blueprint(crud)

# ---------------------------------------用户和注册--------------------------
app.register_blueprint(user)

# ---------------------------------------mpf--------------------------------
app.register_blueprint(mpf)

# ---------------------------------------retrieve--------------------------------
app.register_blueprint(retrieve)

# ---------------------------------------dashboard--------------------------------
app.register_blueprint(dashboard)

# ---------------------------------------pipeline--------------------------------
app.register_blueprint(pipeline_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0")