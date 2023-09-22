from flask import Flask, request, jsonify, send_file
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

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
jwt = JWTManager(app)
app.secret_key = "cuhkdiir"
client = MongoClient("mongodb://localhost:27017")
db = client["Dicom"]

UPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


@app.route("/upload", methods=["POST"])
def upload():
    files = []
    for key in request.files.keys():
        if key.startswith("file"):
            files.extend(request.files.getlist(key))

    if len(files) == 0:
        return "No files uploaded."

    client_ip = request.remote_addr
    collection_name = f"collection_{client_ip.replace('.', '_')}"
    if db.get_collection(collection_name) is not None:
        collection = db[collection_name]
    else:
        collection = db.create_collection(collection_name)
    for file in files:
        if file.filename == "":
            return "Empty filename."

        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)

        ds = pydicom.dcmread(file_path)
        sop_instance_uid = ds.SOPInstanceUID
        existing_doc = collection.find_one({"sopInstanceUID": sop_instance_uid})

        if existing_doc is None:
            patient_name = ds.PatientName
            pixel_size = {"width": ds.Columns, "height": ds.Rows}
            pixel_data_type = ds.pixel_array.dtype.name

            dicom_metadata = {
                "fileName": file.filename,
                "sopInstanceUID": sop_instance_uid,
                "patientName": str(patient_name),
                "pixelSize": pixel_size,
                "pixelDataType": pixel_data_type,
                "address": file_path,
                "clientIP": client_ip,
            }
            collection.insert_one(dicom_metadata)

    return "Success Loaded"


@app.route("/search_by_ip", methods=["GET"])
def search_data_by_ip():
    client_ip = request.remote_addr
    collection_name = f"collection_{client_ip.replace('.', '_')}"
    collection = db[collection_name]
    matched_data = collection.find({"clientIP": client_ip})
    data_list = list(matched_data)

    res = []
    for data in data_list:
        filtered_data = {}
        for key, value in data.items():
            if key != "_id":
                filtered_data[key] = value
        res.append(filtered_data)
    return jsonify(res)


@app.route("/get_file", methods=["GET"])
def get_file():
    file_address = request.args.get("fileAddress")

    # 根据文件地址发送文件内容作为响应
    return send_file(file_address)


# ---------------------------------------用户和注册--------------------------
users_collection = db["users"]

# # 注销
# @app.route("/logout")
# def logout():
#     # 清除用户登录状态
#     session.pop("username", None)
#     return redirect("/login")


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


# ---------------------------------------用户和注册--------------------------


# @app.route("/", defaults={"path": ""})
# @app.route("/<path:path>")
# def catch_allroute(path):
#     return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0")
