from flask import jsonify, request, Blueprint, abort, g
from middleware import token_required, permission_check
from sqlalchemy import and_
from db_models import db, Group, Acc_Group
from notifications import _send_message

groups = Blueprint("groups", __name__)

@groups.route("/create_group", methods=["POST"])
@token_required()
def create_group():
    try:
        data = request.get_json()
        group_name = data.get("group_name")
        description = data.get("description")

        if not group_name:
            return jsonify({"message": "Missing group_name"}), 400

        new_group = Group(
            group_name=group_name, description=description, owner=g.account_id
        )
        db.session.add(new_group)
        db.session.commit()

        acc_group_map = Acc_Group(
            acc_id=g.account_id,
            group_id=new_group.id,
            editable=True,
            can_upload_dataset=True,
            is_owner=True,
        )
        db.session.add(acc_group_map)
        db.session.commit()

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@groups.route("/delete_group", methods=["DELETE"])
@token_required()
def delete_group():
    try:
        group_id = request.args["group_id"]
        group = Group.query.filter(
            and_(Group.id == group_id, Group.owner == g.account_id)
        ).first()
        if group is None:
            abort(404, description="Group not found or you are not the group owner")

        if group.valid:
            group.valid = False
            all_acc_group_pairs = Acc_Group.query.filter_by(group_id=group_id).all()
            for x in all_acc_group_pairs:
                x.status = 2
        else:
            db.session.delete(group)

        db.session.commit()

        group_members = Acc_Group.query.filter(Acc_Group.group_id == group_id).all()
        message = f"Group: {group.group_name} has been deleted."
        group_members_list = [member.acc_id for member in group_members]
        if len(group_members_list) != 0:
            _send_message(message, group_members_list)

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@groups.route("/delete_members_from_group", methods=["DELETE"])
@token_required()
@permission_check(type="group", options="editable")
def delete_members_from_group():
    data = request.get_json()
    user_ids = data.get("user_ids", [])
    group_id = data.get("group_id")

    group = Group.query.filter(
        and_(Group.id == group_id, Group.owner == g.account_id)
    ).first()
    if group is None:
        abort(404, description="Group not found or you are not the group owner")

    acc_groups = Acc_Group.query.filter(
        and_(Acc_Group.acc_id.in_(user_ids), Acc_Group.group_id == group_id)
    ).all()
    for ag in acc_groups:
        ag.status = 2

    db.session.commit()
    message = f"You have been removed from the group: {group.group_name}."
    if len(user_ids) != 0:
        _send_message(message, user_ids)
    return jsonify({"status": "ok"})


@groups.route("/recover_group", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def recover_group():
    group_id = request.get_json()["group_id"]
    group = Group.query.filter(
        and_(Group.id == group_id, Group.owner == g.account_id)
    ).first()
    if group is None:
        abort(404, description="Group not found or you are not the group owner")

    acc_group = Acc_Group.query.filter(
        Acc_Group.group_id == group_id, Acc_Group.acc_id == g.account_id
    ).first()

    group.valid = True
    err = 0
    if acc_group.status == 0 or acc_group.status == 1:
        err = 1
    else:
        acc_group.status = 0
    db.session.commit()

    if err:
        return jsonify({
            "status": "warning",
            "message": "The account group pair already enabled",
        })
    else:
        return jsonify({"status": "ok"})


@groups.route("/recover_group_members", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def recover_group_members():
    try:
        data = request.get_json()
        group_id = data.get("group_id")
        user_ids = data.get("user_ids", [])

        group = Group.query.filter(
            and_(Group.id == group_id, Group.owner == g.account_id)
        ).first()
        if group is None:
            abort(404, description="Group not found or you are not the group owner")

        acc_groups = Acc_Group.query.filter(
            and_(Acc_Group.acc_id.in_(user_ids), Acc_Group.group_id == group_id)
        ).all()
        if acc_groups is None:
            abort(404, description="No member was in the group")

        for x in acc_groups:
            x.status = 0

        db.session.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@groups.route("/update_group_info", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def update_group_info():
    try:
        data = request.get_json()
        group_info = data.get("group_info", {})
        group_id = data.get("group_id")

        group = Group.query.filter(
            and_(Group.id == group_id, Group.owner == g.account_id)
        ).first()

        if group is None:
            abort(404, description="Group not found")
        for key, value in group_info.items():
            if value is not None and value != "":
                setattr(group, key, value)
        db.session.commit()

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@groups.route("/update_group_rights", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def update_group_rights():
    data = request.get_json()
    user_ids = data.get("user_ids", [])
    group_id = data.get("group_id")
    new_rights = data.get("new_rights", {})

    acc_groups = Acc_Group.query.filter(
        and_(Acc_Group.acc_id.in_(user_ids), Acc_Group.group_id == group_id)
    ).all()

    for acc_group in acc_groups:
        for key, value in new_rights.items():
            if value is not None and value != "":
                setattr(acc_group, key, value)

    db.session.commit()

    group = Group.query.filter(Group.id == group_id).first()
    message = f"Your group: {group.group_name} permissions have been updated."
    if len(user_ids) != 0:
        _send_message(message, user_ids)
    return jsonify({"status": "ok"})


@groups.route("/view_members_from_group", methods=["GET"])
@token_required()
def view_members_from_group():
    group_id = request.args["group_id"]
    members = Acc_Group.query.filter(Acc_Group.group_id == group_id).all()

    data = []
    for acc_group in members:
        data.append({
            "account_id": acc_group.belongs_user.id,
            "username": acc_group.belongs_user.username,
            "email": acc_group.belongs_user.email,
            "is_owner": acc_group.is_owner,
            "upload": acc_group.can_upload_dataset,
            "editable": acc_group.editable,
            "status": acc_group.status,
        })
    return jsonify({"status": "ok", "data": data})


@groups.route("/view_groups", methods=["GET"])
@token_required()
def view_groups():
    try:
        groups = Acc_Group.query.filter_by(acc_id=g.account_id).all()
        if groups is None:
            abort(404, "No such groups")

        data = []
        for group in groups:
            group_id = group.group_id
            editable = group.editable
            can_upload_dataset = group.can_upload_dataset
            is_owner = group.is_owner
            status = group.status

            group_info = Group.query.filter_by(id=group_id).first()
            group_name = group_info.group_name
            group_description = group_info.description

            data.append({
                "group_id": group_id,
                "group_name": group_name,
                "editable": editable,
                "can_upload_dataset": can_upload_dataset,
                "owner": is_owner,
                "status": status,
                "group_description": group_description,
            })
        return jsonify({"status": "ok", "data": data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@groups.route("/view_all_groups", methods=["GET"])
@token_required(check_admin=True)
def view_all_groups():
    try:
        groups = Group.query.all()
        if groups is None:
            return jsonify({"status": "ok", "data": []})

        columns = [column.name for column in Group.__table__.columns]
        data = [
            {column: getattr(dataset, column) for column in columns}
            for dataset in groups
        ]
        return jsonify({"status": "ok", "data": data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500