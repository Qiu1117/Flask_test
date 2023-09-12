from flask import Flask, request, render_template, jsonify, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
import pydicom
import os

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "cuhkdiir"
client = MongoClient("mongodb://localhost:27017")
db = client["Dicom"]

UPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


@app.route("/")
def index():
    if "username" not in session:
        return redirect("/login")
    else:
        return render_template("index.html")


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


# ---------------------------------------用户和注册--------------------------
users_collection = db["users"]


# 注册页面
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # 检查用户名是否已存在
        existing_user = users_collection.find_one({"username": username})
        if existing_user:
            return "Username already exists! Please choose a different username."

        # 创建新用户
        hashed_password = generate_password_hash(password)
        new_user = {"username": username, "password": hashed_password}
        users_collection.insert_one(new_user)

        return redirect("/login")

    return render_template("register.html")


# 登录页面
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # 根据用户名查找用户
        user = users_collection.find_one({"username": username})
        if not user or not check_password_hash(user["password"], password):
            return "Invalid username or password."

        session["username"] = username

        return redirect("/dashboard")

    return render_template("login.html")


# 用户仪表盘页面
@app.route("/dashboard")
def dashboard():
    # 检查用户是否已登录
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    return render_template("index.html", username=username)


# 注销
@app.route("/logout")
def logout():
    # 清除用户登录状态
    session.pop("username", None)
    return redirect("/login")


# ---------------------------------------用户和注册--------------------------


if __name__ == "__main__":
    app.run(host="0.0.0.0")
