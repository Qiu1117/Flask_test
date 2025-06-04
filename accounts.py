from flask import jsonify, request, Blueprint, abort, g
from middleware import token_required
from sqlalchemy import and_, or_
from db_models import (
    db, Account, Group, Acc_Group, Dataset_Group, Dataset
)
from notifications import _send_message

accounts = Blueprint("accounts", __name__)

@accounts.route("/get_accounts", methods=["GET"])
@token_required()
def get_accounts():
    username = request.args["username"]
    username_pattern = f"%{username}%"
    users = Account.query.filter(Account.username.like(username_pattern)).all()
    if users is None:
        abort(404, description="No users found")

    data = [
        {"username": user.username, "email": user.email, "account_id": user.id}
        for user in users
    ]
    return jsonify({"status": "ok", "data": data})


@accounts.route("/get_account_info", methods=["GET"])
@token_required()
def get_account_info_route():
    account_id = request.args["account_id"]
    infos = get_account_info(account_id)
    return jsonify({"status": "ok", "data": infos})


@accounts.route("/exit_group", methods=["POST"])
@token_required()
def exit_group():
    data = request.get_json()
    group_id = data.get("group_id")
    acc_group = Acc_Group.query.filter(
        and_(Acc_Group.acc_id == g.account_id, Acc_Group.group_id == group_id)
    ).first()
    if acc_group is None:
        abort(404, description="Not belong to this group")

    if acc_group.status == 2:
        abort(404, description="Already left this group")
    acc_group.status = 2
    db.session.commit()

    group = Group.query.filter(Group.id == group_id).first()
    owner = group.owner
    member = Account.query.filter_by(id=owner).first()
    user = Account.query.filter_by(id=g.account_id).first()
    message = f"User: {user.username} has exited Group: {group.group_name}."
    if len([member.id]) != 0:
        _send_message(message, [member.id])

    return jsonify({"status": "ok"})


def get_account_info(account_id, fetch_type=["account", "notification"]):
    user = Account.query.filter_by(id=account_id).first()
    if user is None:
        abort(404, description="Account not found")

    infos = {}
    
    if "account" in fetch_type or fetch_type == []:
        infos = {
            "account": {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
            },
            "group": [],
            "dataset": [],
        }

    if "notification" in fetch_type:
        infos["notification"] = user.notification

    if "group" in fetch_type:
        acc_groups = Acc_Group.query.filter_by(acc_id=account_id).all()
        for acc_group in acc_groups:
            infos["group"].append({
                "group_id": acc_group.belongs_group.id,
                "group_name": acc_group.belongs_group.group_name,
                "description": acc_group.belongs_group.description,
                "valid": acc_group.belongs_group.valid,
                "owner": acc_group.is_owner,
                "editable": acc_group.editable,
                "can_upload_dataset": acc_group.can_upload_dataset,
            })

    if "dataset" in fetch_type:
        if "group" in fetch_type:
            valid_groups = [
                g.group_id
                for g in acc_groups
                if g.belongs_group.valid and g.status == 0
            ]

            datasets = (
                db.session.query(Dataset, Dataset_Group)
                .join(Dataset_Group, Dataset.id == Dataset_Group.dataset_id)
                .filter(
                    or_(
                        Dataset_Group.group_id.in_(valid_groups),
                        Dataset.owner == account_id,
                    )
                )
                .all()
            )
            infos["dataset"] = []
            for dataset, dataset_group in datasets:
                owner = 1 if str(account_id) == str(dataset.owner) else 0
                if owner:
                    infos["dataset"].append({
                        "dataset_id": dataset.id,
                        "dataset_name": dataset.dataset_name,
                        "owner": owner,
                        "group_id": None,
                        "group_name": None,
                        "group_owner": None,
                        "editable": None,
                        "can_upload_dataset": None,
                    })
                else:
                    group_name = None
                    editable = None
                    can_upload_dataset = None
                    group_owner = None
                    
                    for gr in infos["group"]:
                        if gr["group_id"] == dataset_group.group_id:
                            group_name = gr["group_name"]
                            editable = gr["editable"]
                            can_upload_dataset = gr["can_upload_dataset"]
                            group_owner = gr["owner"]
                            
                    infos["dataset"].append({
                        "dataset_id": dataset.id,
                        "dataset_name": dataset.dataset_name,
                        "owner": owner,
                        "group_id": dataset_group.group_id,
                        "group_name": group_name,
                        "group_owner": group_owner,
                        "editable": editable,
                        "can_upload_dataset": can_upload_dataset,
                    })
        else:
            from datasets import get_accessible_datasets_from_account
            infos["dataset"] = get_accessible_datasets_from_account(account_id)
    return infos