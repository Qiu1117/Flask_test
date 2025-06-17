from flask import Flask, jsonify, request, Response, stream_with_context, Blueprint, abort
from flask import current_app
from db_models import db, Account, Dataset, Group, Acc_Group, Dataset_Group, UserToken
import time
import json
import jwt
from functools import wraps
from flask import g
from sqlalchemy import update, text, func, and_
import redis
from datetime import datetime, timezone

try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    redis_client.ping()  # 测试连接是否成功
    USE_REDIS = True
    print("Redis connected successfully")
except Exception as e:
    USE_REDIS = False
    print(f"Redis connection failed: {str(e)}. Using database fallback.")

def token_required(f=None, *, check_admin=False):
    def decorator(f):
        @wraps(f)
        def inner(*args, **kwargs):
            token = None
            if 'Authorization' in request.headers:
                auth = request.headers['Authorization']
                if auth and len(auth.split(" ")) == 2:
                    token = auth.split(" ")[1]
                    
            if not token:
                return jsonify({"status": "error", "message": "Token is missing"}), 401
                
            try:
                data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
                account_id = data['account_id']
                
                # 使用相同的验证逻辑
                if not verify_stored_token(account_id, token):
                    return jsonify({"status": "error", "message": "Session expired or logged in on another device"}), 401
                    
                g.account_id = account_id
                g.role = data.get('role')
                
                if check_admin and g.role != 1:
                    return jsonify({"status": "error", "message": "Required admin account"}), 401
                
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 401
                
            return f(*args, **kwargs)
        return inner
    
    if f is not None:
        return decorator(f)
    return decorator

def verify_stored_token(user_id, token):
    """验证存储的token是否有效"""
    try:
        if USE_REDIS:
            current_token = redis_client.get(f"user:{user_id}:token")
            if not current_token or current_token.decode() != token:
                return False
            
            is_valid = redis_client.get(f"token:{token}:valid")
            return is_valid is not None
        else:
            token_record = UserToken.query.filter_by(user_id=user_id).first()
            if not token_record or token_record.token != token:
                return False
            
            return datetime.now(timezone.utc) < token_record.expires_at
    except Exception as e:
        print(f"Error verifying token: {str(e)}")
        return False

def permission_check(type=None, options=None):   
    ''' 
        type: 
            - group: check if the user is owner or editable (for )
            - dataset: check if the user is owner  (for dataset operations, include deletion, update, add_dataset_to_group)
            - either: for dataset update and add dataset to group
        options: (only enable when type is 'group')
            - editable: check if the user has permission to edite uploaded dataset
            - can_upload_dataset: check if the user has permission to upload dataset to this group
    ''' 
    def decorated(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if (len(request.form) != 0):
                form_data = request.form
                data = {}
                dataset_data = form_data.get("dataset_data")
                if dataset_data:
                    data = json.loads(dataset_data)
            else:
                data = request.get_json()
            acc_id = g.account_id

            permission = False
            if type == 'group' or type == 'either':
                group_id = data.get('group_id')
                if group_id:
                    group_right = Acc_Group.query.filter(and_(Acc_Group.acc_id==acc_id, 
                                Acc_Group.group_id == group_id)).first()
                    if group_right is None:
                        abort(404, description="Account and Group pair not exist")

                    owner = group_right.is_owner
                    editable = group_right.editable
                    upload = group_right.can_upload_dataset
                    if options == 'can_upload_dataset':
                        permission = True if str(acc_id) == str(owner) or upload else False 
                    elif options == 'editable':
                        permission = True if str(acc_id) == str(owner) or editable else False 
                    else:
                        raise NotImplementedError("Invalid options!")
            if type in ['dataset', 'either']:
                dataset_id = data.get('dataset_id')
                if dataset_id:
                    dataset = Dataset.query.filter_by(id=dataset_id).first()
                    if dataset:
                        dataset_permission = (acc_id == dataset.owner)
                        
                        # Also check if user has group permission for this dataset
                        dataset_groups = Dataset_Group.query.filter_by(
                            dataset_id=dataset_id, valid=True
                        ).all()
                        
                        for dg in dataset_groups:
                            group_right = Acc_Group.query.filter(and_(
                                Acc_Group.acc_id==acc_id,
                                Acc_Group.group_id==dg.group_id,
                                Acc_Group.status == 0
                            )).first()
                            
                            if group_right:
                                if options == 'editable':
                                    dataset_permission = dataset_permission or group_right.editable or group_right.is_owner
                                elif options == 'can_upload_dataset':
                                    dataset_permission = dataset_permission or group_right.can_upload_dataset or group_right.is_owner
                                
                        permission = permission or dataset_permission

            if type not in ['group', 'dataset', 'either']:
                raise NotImplementedError("No such type!")

            if permission:
                return f(*args, **kwargs)
            else:
                return jsonify({"status": "error", "message": "No permission to do this"}), 401
        return inner
    return decorated


if __name__ == "__main__":
    pass
