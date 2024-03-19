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
from db_models import Account, Group, Acc_Group, Dataset_Group


# from middleware import token_required


client = MongoClient("mongodb://127.0.0.1:27017")
db = client["Dicom"]

user = Blueprint("user", __name__)

users_collection = db["users"]


@user.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json()   
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        role = data.get('role')

        if not username or not email or not password:
            return jsonify({'message': 'Missing data'}), 400

        if Account.query.filter_by(username=username).first() is not None:
            return jsonify({'message': 'User already exists'}), 409
        
        new_user = Account(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 用户登录接口
@user.route("/login", methods=["POST"])
def login():
    """
    file: swagger/login.yml
    """
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        login_info = Account.query.filter_by(username=username).first()
        if login_info and check_password_hash(login_info.password_hash, password):
            token = jwt.encode(
                {"account_id": login_info.id, "role": int(login_info.role)},
                current_app.config["SECRET_KEY"],
                algorithm="HS256",
            )
            return jsonify({"status": "ok", "data": {"token": token}})
        else:
            return jsonify({"status": "error", "message": "No such account!"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@user.route("/logout", methods=["GET"])
def logout():
    session.pop("username", None)
    return jsonify({"valid": True, "message": "Logged out successfully"})


def verify_token(check_admin=False):
    def decorated(f):
        @wraps(f)
        def inner(*args, **kwargs):
            token = None

            error_token_missing = 0
            if "Authorization" in request.headers:
                if (
                    request.headers["Authorization"]
                    and len(request.headers["Authorization"].split(" ")) == 2
                ):
                    token = request.headers["Authorization"].split(" ")[1]
                else:
                    error_token_missing = 1
            else:
                error_token_missing = 1
            if not token:
                error_token_missing = 1

            if error_token_missing:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Authentication token is missing or misformated",
                        }
                    ),
                    400,
                )

            try:
                data = jwt.decode(
                    token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
                )
            except Exception as e:
                return jsonify({"status": "error", "message": "Invalid JWT"}), 401

            try:
                role = data["role"]
                g.account_id = data["account_id"]
            except Exception as e:
                return (
                    jsonify(
                        {"status": "error", "message": "Wrong content encoded in JWT"}
                    ),
                    401,
                )

            else:
                if check_admin and role != 1:
                    return (
                        jsonify(
                            {"status": "error", "message": "Required admin account"}
                        ),
                        401,
                    )
                else:
                    return f(*args, **kwargs)
        return inner

    return decorated
