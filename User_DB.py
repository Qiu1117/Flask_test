from flask import Flask, request, jsonify, send_file, session, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from flask import g
from datetime import datetime, timezone, timedelta
from flask import current_app
from db_models import db, Account, Group, Acc_Group, Dataset_Group, UserToken 
from functools import wraps
from CRUD import get_account_info
import redis

user = Blueprint("user", __name__)

try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    redis_client.ping()  
    USE_REDIS = True
    print("Redis connected successfully")
except Exception as e:
    USE_REDIS = False
    print(f"Redis connection failed: {str(e)}. Using database fallback.")

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

def store_token(user_id, token, expiration):
    try:
        if USE_REDIS:
            # 获取旧token
            existing_token = redis_client.get(f"user:{user_id}:token")
            if existing_token:
                # 将旧token标记为无效
                redis_client.delete(f"token:{existing_token.decode()}:valid")
            
            # 存储新token
            token_exp_seconds = int((expiration - datetime.now(timezone.utc)).total_seconds())
            redis_client.set(f"user:{user_id}:token", token, ex=token_exp_seconds)
            redis_client.set(f"token:{token}:valid", "1", ex=token_exp_seconds)
            return True
        else:
            # 删除旧token
            existing_token = UserToken.query.filter_by(user_id=user_id).first()
            if existing_token:
                db.session.delete(existing_token)
            
            # 添加新token
            new_token = UserToken(
                user_id=user_id,
                token=token,
                expires_at=expiration
            )
            db.session.add(new_token)
            db.session.commit()
            return True
    except Exception as e:
        print(f"Error storing token: {str(e)}")
        return False

def verify_stored_token(user_id, token):
    """验证存储的token是否有效"""
    try:
        if USE_REDIS:
            # Redis模式
            current_token = redis_client.get(f"user:{user_id}:token")
            if not current_token or current_token.decode() != token:
                return False
            
            is_valid = redis_client.get(f"token:{token}:valid")
            return is_valid is not None
        else:
            # 数据库模式
            token_record = UserToken.query.filter_by(user_id=user_id).first()
            if not token_record or token_record.token != token:
                return False
            
            # 检查是否过期
            return datetime.now(timezone.utc) < token_record.expires_at
    except Exception as e:
        print(f"Error verifying token: {str(e)}")
        return False

def clear_token(user_id, token):
    """清除用户token"""
    try:
        if USE_REDIS:
            # Redis模式
            redis_client.delete(f"token:{token}:valid")
            redis_client.delete(f"user:{user_id}:token")
        else:
            # 数据库模式
            token_record = UserToken.query.filter_by(user_id=user_id).first()
            if token_record:
                db.session.delete(token_record)
                db.session.commit()
        return True
    except Exception as e:
        print(f"Error clearing token: {str(e)}")
        return False

@user.route("/login", methods=["POST"])
def login():
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

            if remember_me:
                expiration = datetime.now(timezone.utc) + timedelta(days=3)
            else:
                expiration = datetime.now(timezone.utc) + timedelta(days=1)

            token = jwt.encode(
                {"account_id": login_info.id, 
                 "role": int(login_info.role),
                 "exp": expiration,
                 "iat": datetime.now(timezone.utc)
                },
                current_app.config["SECRET_KEY"],
                algorithm="HS256",
            )
            
            store_token(login_info.id, token, expiration)
            
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
    try:
        if 'account_id' in session:
            user_id = session['account_id']
            token = None
            
            # 获取当前token
            if 'Authorization' in request.headers:
                auth = request.headers['Authorization']
                if auth and len(auth.split(" ")) == 2:
                    token = auth.split(" ")[1]
            
            # 清除token
            if token:
                clear_token(user_id, token)
    except Exception as e:
        print(f"Error during logout: {str(e)}")
    
    session.clear()
    return jsonify({"valid": True, "message": "Logged out successfully"})

def verify_token(check_admin=False):
    def decorated(f):
        @wraps(f)
        def inner(*args, **kwargs):
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
                account_id = data["account_id"]
                g.account_id = account_id
                g.role = role
                
                # 验证token是否是该用户的有效token
                if not verify_stored_token(account_id, token):
                    return jsonify({"status": "error", "message": "Session expired or logged in on another device"}), 401
                
                # 更新session活动时间
                session['last_activity'] = datetime.now(timezone.utc).timestamp()
            except Exception as e:
                return (
                    jsonify(
                        {"status": "error", "message": f"JWT validation error: {str(e)}"}
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