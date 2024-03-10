from flask import Flask, request, jsonify, send_file, session, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    decode_token,
    jwt_required,
    get_jwt_identity,
)
from jwt.exceptions import ExpiredSignatureError
from bson.objectid import ObjectId
from pymongo import MongoClient
from functools import wraps


# from middleware import token_required


client = MongoClient("mongodb://127.0.0.1:27017")
db = client["Dicom"]

user = Blueprint("user", __name__)

users_collection = db["users"]


@user.route("/register", methods=["POST"])
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
@user.route("/login", methods=["POST"])
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


@user.route("/logout", methods=["GET"])
def logout():
    session.pop("username", None)
    return jsonify({"valid": True, "message": "Logged out successfully"})


def verify_token(check_admin=False):
    def decorated(f):
        @wraps(f)
        def inner(*args, **kwargs):
            token = None

            if "token" in request.headers:
                token = request.headers["token"]
            try:
                decoded_token = decode_token(token)
                user_id = decoded_token["sub"]
                user = users_collection.find_one({"_id": ObjectId(user_id)})
                # if user:
                #     return jsonify({"valid": True, "sub": user_id})
                return f(*args, **kwargs)
            except ExpiredSignatureError:
                return jsonify({"valid": False, "message": "Token has expired"})
            except Exception as e:
                return jsonify({"valid": False, "message": "Invalid token"})

        return inner

    return decorated
