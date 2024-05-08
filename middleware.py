from flask import Flask, jsonify, request, Response, stream_with_context, Blueprint, abort
from flask import current_app
from db_models import db, Account, Dataset, Group, Acc_Group, Dataset_Group

import time
import json
import jwt
from functools import wraps
from flask import g
from sqlalchemy import update, text, func, and_
from werkzeug.exceptions import BadRequest

def token_required(check_admin=False):
    def decorated(f):
        @wraps(f)
        def inner(*args, **kwargs):
            token = None

            error_token_missing = 0
            if "Authorization" in request.headers:
                if request.headers["Authorization"] and len(request.headers["Authorization"].split(" ")) == 2:
                    token = request.headers["Authorization"].split(" ")[1]  
                else:
                    error_token_missing = 1
            else:
                error_token_missing = 1
            if not token:
                error_token_missing = 1
                
            if error_token_missing:
                return jsonify({
                    "status": "error",
                    "message": "Authentication token is missing or misformated"
                }), 400
            
            try:
                data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
            except Exception as e:
                return jsonify({"status": "error", "message": "Invalid JWT"}), 401

            try:
                role = data['role']
                g.account_id = data['account_id']
            except Exception as e:
                return jsonify({"status": "error", "message": "Wrong content encoded in JWT"}), 401
            
            else:
                if check_admin and role != 1:
                    return jsonify({"status": "error", "message": "Required admin account"}), 401
                else:
                    return f(*args, **kwargs)
        return inner
    return decorated


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
            if type == 'dataset' or type == 'either':
                dataset_id = data.get('dataset_id')
                dataset = Dataset.query.filter_by(id=dataset_id).first()
                if dataset is None:
                    abort(404, description="Dataset not found")
                owner = dataset.owner
                permission = permission or (True if str(acc_id) == str(owner) else False)

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
