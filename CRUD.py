from flask import Flask, jsonify, request, Response, stream_with_context, Blueprint, abort
import time
import sqlite3
from User_DB import verify_token
import json
import shortuuid
from flask import g
from flask_cors import CORS
from db_models import db, Account, Group, Acc_Group, Dataset_Group
from sqlalchemy.types import Unicode

crud = Blueprint('crud', __name__)



@crud.route(
    "/get_accounts", methods=["GET"]
)  # use when search users like github invitation
@verify_token()
def get_accounts():
    username = request.args['username']
    users = Account.filter_by(username=username).query.with_entities(Account.username, Account.id).all()
    if users is None:
        abort(404, description="Group not found")

    data = [{'username': user.username, 'accound_id': user.id} for user in users]
    
    return jsonify({"status": "ok", "data": data})


@crud.route(
    "/accept_group_invi", methods=["POST"]
)  # use when search users like github invitation
@verify_token()
def accept_group_invi():
    data = request.get_json()
    group_id = data['group_id']
    note_id = data['note_id']

    acc_group_map = Acc_Group.query.filter_by(acc_id=g.account_id,group_id=group_id).first()
    acc_group_map.status = 0
    
    account = Account.query.filter_by(id=g.account_id).first()
    account.notification[note_id]['status'] = 2
    db.session.commit()
    
    return jsonify({"status": "ok"})


@crud.route("/invite_acc_to_group", methods=["POST"])
@verify_token()
def invit_acc_to_group():
    try:
        data = request.get_json()
        acc_id = data['accound_id']
        group_id = data['group_id']

        group = Group.query.filter_by(id=group_id).first()
        if group is None:
            abort(404, description="Group not found")
        exist_pair = Acc_Group.query.filter_by(group_id=data['group_id'], acc_id=acc_id).first()
        if exist_pair:
            if exist_pair.status == 0:
                abort(404, description="Group already exist")
            elif exist_pair.status == 1:
                abort(404, description="Invitation already sent")
            elif exist_pair.status == 2:
                exist_pair.status = 1
                db.session.add(exist_pair)
                db.session.commit()
                return jsonify({"status": "ok"})
        else:
            acc_group_map = Acc_Group(
                                    acc_id=acc_id,
                                    group_id=group_id,
                                    editable=False,
                                    can_upload_dataset=False,
                                    owner=False,
                                    status=1 # pending 
                                )
            db.session.add(acc_group_map)

            account = Account.query.filter_by(id=g.account_id).first()
            uid = shortuuid()
            account.notification[uid] = {'message': f"{g.account_id} invite you to {group.group_name} group", 
                                            'response_route': '/accept_group_invi',
                                            'content': {'group_id':group_id},
                                            'status': 1,
                                            'uid': uid}  # 0 for inactive, 1 for active, 2 for solved
            db.session.commit()

            return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@crud.route("/create_group", methods=["POST"])
@verify_token()
def create_group():
    try:
        data = request.get_json()   
        group_name = data.get('group_name')
        description = data.get('description')

        if not group_name:
            return jsonify({'message': 'Missing group_name'}), 400
        
        new_group = Group(
            group_name=group_name,
            description=description
        )
        db.session.add(new_group)
        db.session.commit()

        acc_group_map = Acc_Group(
                                acc_id=g.account_id,
                                group_id=new_group.id,
                                editable=True,
                                can_upload_dataset=True,
                                owner=True
                            )

        db.session.add(acc_group_map)
        db.session.commit()

        return jsonify({"status": "ok"})
    except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500


@crud.route("/delete_group", methods=["DELETE"])
@verify_token()
def delete_group():
    try:
        group_id = request.args['group_id']
        group = Group.query.filter_by(id=group_id).first()
        if group is None:
            abort(404, description="Group not found")

        group.invalid = 1
        db.session.commit()

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@crud.route("/view_groups", methods=["GET"])  # get all groups of this user
@verify_token()
def view_groups():
    try:
        groups = Acc_Group.query.filter_by(acc_id=g.account_id).all()
        if groups is None:
            return jsonify({"status": "ok", "data": []})
        data = []
        for group in groups:
            group_id = group.group_id
            editable = group.editable
            can_upload_dataset = group.can_upload_dataset
            owner = group.owner
            status = group.status

            group_info = Group.query.filter_by(id=group_id).first()
            group_name = group_info.group_name
            group_description = group_info.description

            data.append({'group_id': group_id, 
                         'group_name': group_name,
                         'editable': editable, 
                         'can_upload_dataset': can_upload_dataset,
                         'owner': owner,
                         'status': status,
                         'group_description': group_description})
        return jsonify({"status": "ok", "data": data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@crud.route("/view_all_groups", methods=["GET"])  # get all groups, only used by admin
@verify_token(check_admin=True)
def view_all_groups():
    try:
        groups = Group.query.all()
        if groups is None:
            return jsonify({"status": "ok", "data": []})
        
        columns = [column.name for column in Group.__table__.columns]
        data = [{column:getattr(dataset,column) for column in columns} for dataset in groups]
        return jsonify({"status": "ok", "data": data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    pass
