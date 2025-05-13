from flask import Flask, request, jsonify, send_file, session, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from flask import g
from datetime import datetime, timezone, timedelta
from flask import current_app
from db_models import db
from functools import wraps
from db_models import Account, Group, Acc_Group, Dataset_Group
from CRUD import get_account_info


user = Blueprint("user", __name__)


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


@user.route("/login", methods=["POST"])
def login():
    """
    file: swagger/login.yml
    """
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        remember_me = data.get("remember_me", False)
        fetch = data.get("fetch_type", [])

        login_info = Account.query.filter_by(username=username).first()
        if login_info and check_password_hash(login_info.password_hash, password):

            login_info.last_login = datetime.now(timezone.utc)
            db.session.commit()

            expiration = datetime.now(timezone.utc) + timedelta(days=1)

            if remember_me:
                expiration = datetime.now(timezone.utc) + timedelta(days=3)  # longer expiration for remember me
            else:
                expiration = datetime.now(timezone.utc) + timedelta(days=1)  # shorter session

            token = jwt.encode(
                {"account_id": login_info.id, 
                 "role": int(login_info.role),
                 "exp": expiration
                },
                current_app.config["SECRET_KEY"],
                algorithm="HS256",
            )
            if fetch:
                infos = get_account_info(login_info.id, fetch)
            else:
                infos = get_account_info(login_info.id)

            session['username'] = username
            session['account_id'] = login_info.id
            session['last_activity'] = datetime.now(timezone.utc).timestamp()

            if remember_me:
                session.permanent = True
                current_app.permanent_session_lifetime = timedelta(days=3)
            else:
                session.permanent = True
                current_app.permanent_session_lifetime = timedelta(days=1)

            return jsonify({"status": "ok", "data": {"token": token, "infos": infos}})
        else:
            return jsonify({"status": "error", "message": "No such account!"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@user.route("/logout", methods=["GET"])
def logout():
    session.pop("username", None)
    return jsonify({"valid": True, "message": "Logged out successfully"})

def check_session_timeout():
    """Helper function to check if the session has timed out"""
    if 'last_activity' in session:
        current_time = datetime.now(timezone.utc).timestamp()
        last_activity = session.get('last_activity')
        max_idle = current_app.permanent_session_lifetime.total_seconds()
        
        if current_time - last_activity > max_idle:
            session.clear()
            return False
        
        # Update the last activity time
        session['last_activity'] = current_time
    return True


def verify_token(check_admin=False):
    def decorated(f):
        @wraps(f)
        def inner(*args, **kwargs):
            # First check if session is still valid
            if not check_session_timeout():
                return jsonify({"status": "error", "message": "Session expired"}), 401
                
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
                            "message": "Authentication token is missing or misformatted",
                        }
                    ),
                    400,
                )

            try:
                data = jwt.decode(
                    token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
                )
            except jwt.ExpiredSignatureError:
                return jsonify({"status": "error", "message": "Token expired"}), 401
            except Exception as e:
                return jsonify({"status": "error", "message": "Invalid JWT"}), 401

            try:
                role = data["role"]
                g.account_id = data["account_id"]
                g.role = role
                
                # Update session last activity
                session['last_activity'] = datetime.now(timezone.utc).timestamp()
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

