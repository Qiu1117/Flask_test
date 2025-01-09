from flask import (
    Flask,
    jsonify,
    request,
    Blueprint,
    abort,
    make_response,
    send_file
)
from middleware import token_required, permission_check
import json
import os
import shortuuid
from flask import g
from flask_cors import CORS
from collections import defaultdict
from db_models import (
    db,
    Account,
    Group,
    Acc_Group,
    Dataset_Group,
    Dataset,
    Patient,
    Dataset_Patients,
    Study,
    Dataset_Studies,
    Series,
    Dataset_Series,
    Dataset_Instances,
)
from sqlalchemy.types import Unicode
from sqlalchemy import update, text, func, and_, or_
import sqlalchemy
import requests
import pydicom


crud = Blueprint("crud", __name__)
orthanc_url = "http://127.0.0.1:8042"


# ------------------------------------------ Notification --------------------------------------
@crud.route("/get_notifications", methods=["GET"])
@token_required()
def get_notifications():
    acc_id = g.account_id
    notifications = Account.query.filter_by(id=acc_id).first().notification
    return jsonify({"status": "ok", "data": notifications})


@crud.route(
    "/process_group_invi", methods=["POST"]
)  # use when search users like github invitation
@token_required()
def process_group_invi():
    data = request.get_json()
    accept = data["accept"]
    group_id = data["group_id"]
    note_id = data["note_id"]

    if (
        accept
    ):  # modify the group and account pair and reset the status of the notification
        acc_group_map = Acc_Group.query.filter_by(
            acc_id=g.account_id, group_id=group_id
        ).first()
        acc_group_map.status = 0  # enable

    # always reset the status of the notification no matter accept or reject
    account = Account.query.filter_by(id=g.account_id).first()
    if note_id in account.notification.keys():
        update_query = text(
            """
            UPDATE "Account"
            SET notification = jsonb_set(notification, ARRAY[:uid, 'status'], '2')
            WHERE id = :id
        """
        )
        db.session.execute(update_query, {"uid": note_id, "id": g.account_id})
        db.session.commit()
        return jsonify({"status": "ok"})
    else:
        return (
            jsonify(
                {"status": "error", "message": "The notification not belong to you!"}
            ),
            500,
        )


@crud.route("/invite_acc_to_group", methods=["POST"])
@token_required()
def invit_acc_to_group():
    data = request.get_json()
    acc_id = data["account_id"]
    group_id = data["group_id"]

    group = Group.query.filter_by(id=group_id).first()
    if group is None:
        abort(404, description="Group not found")
    exist_pair = Acc_Group.query.filter_by(
        group_id=data["group_id"], acc_id=acc_id
    ).first()
    if exist_pair:
        if exist_pair.status == 0:
            abort(404, description="Group already exist")
        elif exist_pair.status == 1:
            abort(404, description="Invitation already sent")
        elif exist_pair.status == 2:
            exist_pair.status = 1
            db.session.commit()
            return jsonify({"status": "ok"})
        return jsonify(
            {"status": "ok"}
        )  # this line only for flask requirement (must end with return)
    else:
        acc_group_map = Acc_Group(
            acc_id=acc_id,
            group_id=group_id,
            editable=False,
            can_upload_dataset=False,
            is_owner=False,
            status=1,  # pending
        )
        db.session.add(acc_group_map)

        uid = shortuuid.uuid()
        note = {
            uid: {
                "message": f"User: {g.account_id} invite you to Group: {group.group_name}",
                "response_route": "/accept_group_invi",
                "content": {"group_id": group_id},
                "status": 0,  # 0 for active, 1 for inactive, 2 for solved
                "uid": uid,
            }
        }
        update_query = text(
            """
            UPDATE "Account"
            SET notification = notification || :note
            WHERE id=:id
        """
        )
        db.session.execute(update_query, {"note": json.dumps(note), "id": acc_id})
        db.session.commit()
        return jsonify({"status": "ok"})


@crud.route("/send_message", methods=["POST"])  # get all groups of this user
@token_required()
def send_message():
    data = request.get_json()
    target_users = data["target_users"]  # user id
    message = data["message"]

    _send_message(message, target_users)
    return jsonify({"status": "ok"})


def _send_message(message, target_users):
    # Account.query.filter_by(id=g.account_id).update()
    uid = shortuuid.uuid()
    note = {
        uid: {
            "message": message,
            "response_route": "",
            "content": "",
            "status": 1,
            "uid": uid,
        }
    }

    update_query = text(
        """
        UPDATE "Account"
        SET notification = notification || :note
        WHERE id in :id
    """
    )
    db.session.execute(
        update_query, {"note": json.dumps(note), "id": tuple(target_users)}
    )
    # db.session.execute(update_query, {'note': json.dumps(note), 'id': 1})
    db.session.commit()


@crud.route("/read_message", methods=["POST"])
@token_required()
def read_message():
    data = request.get_json()
    note_id = data["note_id"]
    account = Account.query.filter_by(id=g.account_id).first()
    if note_id in account.notification.keys():
        update_query = text(
            """
            UPDATE "Account"
            SET notification = jsonb_set(notification, ARRAY[:uid, 'status'], '2')
            WHERE id = :id
        """
        )
        db.session.execute(update_query, {"uid": note_id, "id": g.account_id})
        db.session.commit()
        return jsonify({"status": "ok"})
    else:
        return (
            jsonify(
                {"status": "error", "message": "The notification not belong to you!"}
            ),
            500,
        )


# ------------------------------------------ Dataset --------------------------------------
@crud.route(
    "/create_dataset", methods=["POST"]
)  # will simultaneously create a default group for this dataset
@token_required()
def create_dataset():
    data = request.get_json()
    dataset_info = data.get("dataset_info", {})

    # add this dataset to its default group
    dataset_name = dataset_info.get("dataset_name", "anonymous")
    default_group_name = f"default_{dataset_name}"
    default_group = Group(
        group_name=default_group_name,
        description=f"This is a default group for dataset {dataset_name}",
        owner=g.account_id,
    )
    db.session.add(default_group)
    db.session.commit()

    acc_group = Acc_Group(
        acc_id=g.account_id,
        group_id=default_group.id,
        is_owner=True,
        editable=True,
        can_upload_dataset=True,
        status=0,
    )
    db.session.add(acc_group)
    db.session.commit()

    new_dataset = Dataset(owner=g.account_id, **dataset_info)
    db.session.add(new_dataset)
    db.session.commit()

    new_data_group = Dataset_Group(group_id=default_group.id, dataset_id=new_dataset.id)
    db.session.add(new_data_group)
    db.session.commit()

    return jsonify({"status": "ok"})


@crud.route(
    "/add_dataset_to_groups", methods=["POST"]
)  # will simultaneously create a default group for this dataset
@token_required()
@permission_check(type="either", options="upload")
def add_groups_to_dataset():
    data = request.get_json()
    dataset_id = data.get("dataset_id")
    group_ids = data.get("group_ids", [])

    group = Group.query.filter(Group.id.in_(group_ids)).all()
    exist_group = [str(g.id) for g in group]
    if len(exist_group) != len(group_ids):
        abort(404, "Some groups do not exist")

    # check exist pairs, re-valid and ignore them
    exist_pairs = Dataset_Group.query.filter(
        and_(
            Dataset_Group.dataset_id == dataset_id,
            Dataset_Group.group_id.in_(group_ids),
        )
    ).all()
    exist_group_id = [x.group_id for x in exist_pairs]
    err = []
    if exist_pairs:
        for i in exist_pairs:
            if i.valid:
                err.append(str(i.group_id))
            else:
                i.valid = True
    # add new pair only for non-exist ones
    operation_group_id = [x for x in group_ids if x not in exist_group_id]
    for group_id in operation_group_id:
        new_data_group = Dataset_Group(group_id=group_id, dataset_id=dataset_id)
        db.session.add(new_data_group)

    db.session.commit()

    member_list = _get_members_from_groups(group_ids, False)
    target_dataset = Dataset.query.filter_by(id=dataset_id).first()
    message = (
        f"The dataset: {target_dataset.dataset_name} has been added to your group."
    )
    if len(member_list) != 0:
        _send_message(message, member_list)

    if err:
        return jsonify(
            {
                "status": "warning",
                "message": f"Group {' '.join(err)} have been on the dataset",
            }
        )
    else:
        return jsonify({"status": "ok"})


def _get_members_from_groups(group_ids, verbose=False):
    # Get account info from Account Table and get permission info from Acc_Group Table
    member_info = []

    if verbose:
        members = (
            db.session.query(Account, Acc_Group)
            .join(Acc_Group)
            .filter(Acc_Group.group_id.in_(group_ids))
            .all()
        )

        for account, acc_group in members:
            member_info.append(
                {
                    "id": account.id,
                    "username": account.username,
                    "email": account.email,
                    "group_id": acc_group.group_id,
                    "is_owner": acc_group.is_owner,
                    "editable": acc_group.editable,
                    "can_upload_dataset": acc_group.can_upload_dataset,
                    "status": acc_group.status,
                }
            )
    else:
        members = (
            db.session.query(Account, Acc_Group)
            .join(Acc_Group)
            .filter(Acc_Group.group_id.in_(group_ids))
            .all()
        )
        for account, acc_group in members:
            member_info.append(account.id)
    return member_info


@crud.route("/delete_dataset", methods=["DELETE"])
@token_required()
def delete_dataset():
    try:
        dataset_id = request.args["dataset_id"]
        dataset = Dataset.query.filter_by(id=dataset_id).first()
        if dataset is None:
            abort(404, description="Dataset not found")

        if str(dataset.owner) == str(g.account_id):
            dataset_group = Dataset_Group.query.filter_by(dataset_id=dataset_id).all()
            for d in dataset_group:
                d.valid = False
            if dataset.valid:
                dataset.valid = False
            else:
                db.session.delete(dataset)
            db.session.commit()

            members_list = []
            for group in dataset_group:
                members = Acc_Group.query.filter(
                    Acc_Group.group_id == group.group_id
                ).all()
                for member in members:
                    members_list.append(member.acc_id)

            message = f"Dataset:{dataset.dataset_name} has been deleted."
            members_list = list(set(members_list))
            if len(members_list) != 0:
                _send_message(message, members_list)

            return jsonify({"status": "ok"})
        else:
            abort(404, "No rights to delete dataset")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@crud.route("/remove_dataset_from_group", methods=["DELETE"])
@token_required()
@permission_check(type="dataset")
def remove_dataset_from_group():
    data = request.get_json()
    dataset_id = data.get("dataset_id")
    group_ids = data.get("group_ids", [])

    group = Group.query.filter(Group.id.in_(group_ids)).all()
    exist_group = [str(g.id) for g in group]
    if len(exist_group) != len(group_ids):
        abort(404, "Some groups do not exist")

    # check exist pairs, re-valid and ignore them
    exist_pairs = Dataset_Group.query.filter(
        and_(
            Dataset_Group.dataset_id == dataset_id,
            Dataset_Group.group_id.in_(group_ids),
        )
    ).all()
    exist_group_id = [x.group_id for x in exist_pairs]
    if exist_pairs:
        for i in exist_pairs:
            if i.valid:  # first time deletion only invalid the pair
                i.valid = False
            else:
                db.session.delete(exist_pairs)

            tartget_group = Group.query.filter(Group.id == i.group_id).first()
            members = tartget_group.owner
            target_dataset = Dataset.query.filter_by(id=dataset_id).first()
            message = f"Your group: {tartget_group.group_name} has been removed from dataset: {target_dataset.dataset_name}."
            if len([members]) != 0:
                _send_message(message, [members])

        db.session.commit()

        err = [x for x in group_ids if x not in exist_group_id]
        if err:
            return jsonify(
                {
                    "status": "warning",
                    "message": f"Group {' '.join(err)} have been on the dataset",
                }
            )
        else:
            return jsonify({"status": "ok"})
    else:
        abort(404, "None of the given id pairs are exist")


@crud.route("/recover_dataset", methods=["POST"])
@token_required()
def recover_dataset():
    try:
        data = request.get_json()
        dataset_id = data.get("dataset_id")

        dataset = Dataset.query.filter_by(id=dataset_id).first()
        if dataset is None:
            abort(404, description="Dataset not found")

        if str(dataset.owner) == str(g.account_id):
            dataset_group = Dataset_Group.query.filter_by(dataset_id=dataset_id).all()
            for d in dataset_group:
                d.valid = True
            dataset.valid = True
            db.session.commit()
            return jsonify({"status": "ok"})
        else:
            abort(404, "No rights to recover dataset")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@crud.route("/update_dataset", methods=["POST"])
@token_required()
@permission_check(type="either", options="editable")
def update_dataset():
    data = request.get_json()
    # group_id = data.get('group_id')  # must be sent, but only be used for middleware
    dataset_info = data.get("dataset_info", {})
    dataset_id = data.get("dataset_id")
    dataset = Dataset.query.filter_by(id=dataset_id).first()
    if dataset is None:
        abort(404, description="Dataset not found")

    # in this way, even the request does not contain specific attribute it wont update a empty value
    for key, value in dataset_info.items():
        if value is not None and value != "":
            setattr(dataset, key, value)

    db.session.commit()

    members = dataset.owner
    message = f"Your dataset: {dataset.dataset_name} has been updated."
    if len([members]) != 0:
        _send_message(message, [members])
    return jsonify({"status": "ok"})


@crud.route("/view_groups_from_dataset", methods=["GET"])
@token_required()
def view_groups_from_dataset():
    dataset_id = request.args["dataset_id"]
    # groups = db.session.query(Group, Dataset_Group).join(Dataset_Group, Group.id==Dataset_Group.group_id) \
    #                .filter(Dataset_Group.dataset_id == dataset_id).all()

    dataset_groups = Dataset_Group.query.filter(
        Dataset_Group.dataset_id == dataset_id
    ).all()
    if dataset_groups is None:
        abort(404, description="No group was found")

    data = []
    for dataset_group in dataset_groups:
        data.append(
            {
                "group_id": dataset_group.group_id,
                "name": dataset_group.belongs.group_name,
                "description": dataset_group.belongs.description,
                "group_valid": dataset_group.belongs.valid,
                "dataset_group_valid": dataset_group.valid,
            }
        )
    return jsonify({"status": "ok", "data": data})


@crud.route("/view_datasets_from_account", methods=["GET"])
@token_required()
def view_datasets_from_account():
    given_id = request.args.get("account_id")
    acc_id = given_id if given_id else g.account_id

    data = _get_accessible_datasets_from_account(acc_id)

    return jsonify({"status": "ok", "data": data})


def _get_accessible_datasets_from_account(account_id):
    data = []
    datasets = (
        db.session.query(Acc_Group, Dataset_Group, Group, Dataset)
        .filter(
            and_(
                Dataset_Group.dataset_id == Dataset.id,
                Group.id == Dataset_Group.group_id,
                Acc_Group.group_id == Group.id,
                Acc_Group.acc_id == account_id,
                or_(
                    and_(Group.valid, Dataset_Group.valid, Acc_Group.status == 0),
                    Dataset.owner == account_id,
                ),
            )
        )
        .all()
    )

    for acc_group, dataset_group, group, dataset in datasets:
        owner = 1 if str(dataset.owner) == str(account_id) else 0
        if owner:
            data.append(
                {
                    "group_id": None,
                    "group_name": None,
                    "dataset_id": dataset.id,
                    "dataset_name": dataset.dataset_name,
                    "valid": dataset.valid,
                    "owner": owner,
                    "editable": None,
                    "can_upload_dataset": None,
                }
            )
        else:
            data.append(
                {
                    "group_id": group.id,
                    "group_name": group.group_name,
                    "dataset_id": dataset.id,
                    "dataset_name": dataset.dataset_name,
                    "valid": dataset.valid,
                    "owner": owner,
                    "editable": acc_group.editable,
                    "can_upload_dataset": acc_group.can_upload_dataset,
                }
            )
    return data


@crud.route("/view_all_datasets", methods=["GET"])
@token_required()
def view_all_datasets():
    try:
        datasets = Dataset.query.all()
        columns = [column.name for column in Dataset.__table__.columns]
        data = [
            {column: getattr(dataset, column) for column in columns}
            for dataset in datasets
        ]

        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------------------------------ Account --------------------------------------


@crud.route(
    "/get_accounts", methods=["GET"]
)  # use when search users like github invitation
@token_required()
def get_accounts():
    username = request.args["username"]
    username_pattern = f"%{username}%"
    users = Account.query.filter(Account.username.like(username_pattern)).all()
    if users is None:
        abort(404, description="Group not found")

    data = [
        {"username": user.username, "email": user.email, "account_id": user.id}
        for user in users
    ]

    return jsonify({"status": "ok", "data": data})


@crud.route(
    "/get_account_info", methods=["GET"]
)  # use when search users like github invitation
@token_required()
def get_account_info():
    account_id = request.args["account_id"]
    infos = get_account_info(account_id)
    return jsonify({"status": "ok", "data": infos})


def get_account_info(account_id, fetch_type=["account", "notification"]):
    """
    fetch_type: list, which include the following enum, order does not matter
        - account: basic account info w/o notification
        - notification: notification of this account
        - group: group which the account belong to, include the permission
        - dataset: dataset the account can access
    """
    user = Account.query.filter_by(id=account_id).first()
    if user is None:
        abort(404, description="Group not found")

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

    # group info
    if "group" in fetch_type:
        acc_groups = Acc_Group.query.filter_by(acc_id=account_id).all()
        for acc_group in acc_groups:
            infos["group"].append(
                {
                    "group_id": acc_group.belongs_group.id,
                    "group_name": acc_group.belongs_group.group_name,
                    "description": acc_group.belongs_group.description,
                    "valid": acc_group.belongs_group.valid,
                    "owner": acc_group.is_owner,
                    "editable": acc_group.editable,
                    "can_upload_dataset": acc_group.can_upload_dataset,
                }
            )

    # dataset info
    if "dataset" in fetch_type:
        if "group" in fetch_type:  # can save SQL time
            valid_groups = [
                g.id
                for a_g in acc_groups
                if a_g.belongs_group.valid and a_g.status == 1
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
                owner = 1 if account_id == dataset.owner else 0
                if owner:
                    infos["dataset"].append(
                        {
                            "dataset_id": dataset.id,
                            "dataset_name": dataset.dataset_name,
                            "owner": owner,
                            "group_id": None,
                            "group_name": None,
                            "group_owner": None,
                            "editable": None,
                            "can_upload_dataset": None,
                        }
                    )
                else:
                    for gr in infos["group"]:
                        if g["group_id"] == dataset_group.group_id:
                            group_name = gr["group_name"]
                            editable = gr["editable"]
                            can_upload_dataset = gr["can_upload_dataset"]
                            group_owner = gr["is_owner"]
                    infos["dataset"].append(
                        {
                            "dataset_id": dataset.id,
                            "dataset_name": dataset.dataset_name,
                            "owner": owner,
                            "group_id": dataset_group.group_id,
                            "group_name": group_name,
                            "group_owner": group_owner,
                            "editable": editable,
                            "can_upload_dataset": can_upload_dataset,
                        }
                    )
        else:
            infos["dataset"] = _get_accessible_datasets_from_account(account_id)
    return infos


@crud.route("/exit_group", methods=["POST"])  # user exit group
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


# ------------------------------------------ Group --------------------------------------


@crud.route("/create_group", methods=["POST"])
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


@crud.route("/delete_group", methods=["DELETE"])
@token_required()
def delete_group():
    try:
        group_id = request.args["group_id"]
        group = Group.query.filter(
            and_(Group.id == group_id, Group.owner == g.account_id)
        ).first()
        if group is None:
            abort(
                404,
                description="Group not found or you are not the group owner to do this operation",
            )

        if group.valid:
            group.valid = False  # put in the recycle bin

            all_acc_group_pairs = Acc_Group.query.filter_by(group_id=group_id).all()
            for x in all_acc_group_pairs:
                x.status = 2
        else:  # if already in the recycle bin, cascade and permenant delete
            db.session.delete(group)

        db.session.commit()

        group_members = Acc_Group.query.filter(Acc_Group.group_id == group_id).all()
        message = f"Group: {group.group_name} has been deleted."
        group_members_list = []
        for member in group_members:
            group_members_list.append(member.acc_id)
        if len(group_members_list) != 0:
            _send_message(message, group_members_list)

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# can only delete once, cant permenant delete, bec group owner must always invite back members not recover members
@crud.route("/delete_members_from_group", methods=["DELETE"])
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
        abort(
            404,
            description="Group not found or you are not the group owner to do this operation",
        )

    acc_groups = Acc_Group.query.filter(
        and_(Acc_Group.acc_id.in_(user_ids), Acc_Group.group_id == group_id)
    ).all()
    for ag in acc_groups:
        ag.status = 2

    db.session.commit()
    members = user_ids
    message = f"You have been removed from the group: {group.group_name}."
    if len(members) != 0:
        _send_message(message, members)
    return jsonify({"status": "ok"})


@crud.route("/recover_group", methods=["POST"])  # recover deleted group
@token_required()
@permission_check(type="group", options="editable")
def recover_group():
    group_id = request.get_json()["group_id"]
    group = Group.query.filter(
        and_(Group.id == group_id, Group.owner == g.account_id)
    ).first()
    if group is None:
        abort(
            404,
            description="Group not found or you are not the group owner to do this operation",
        )

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
        return jsonify(
            {
                "status": "warning",
                "message": "The account group pair already enabled, which should be wrong",
            }
        )
    else:
        return jsonify({"status": "ok"})


@crud.route(
    "/recover_group_members", methods=["POST"]
)  # recover invalid member from deleted group
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
            abort(
                404,
                description="Group not found or you are not the group owner to do this operation",
            )

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


@crud.route(
    "/update_group_info", methods=["POST"]
)  # only update group name and description
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


@crud.route(
    "/update_group_rights", methods=["POST"]
)  # given target users update theirs rights
@token_required()
@permission_check(type="group", options="editable")
def update_group_rights():
    data = request.get_json()
    acc_id = g.account_id
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

    members = user_ids
    group = Group.query.filter(Group.id == group_id).first()
    message = f"Your group: {group.group_name} permissions have been updated."
    if len(members) != 0:
        _send_message(message, members)
    return jsonify({"status": "ok"})


@crud.route("/view_members_from_group", methods=["GET"])  # get all groups of this user
@token_required()
def view_members_from_group():
    group_id = request.args["group_id"]
    members = Acc_Group.query.filter(Acc_Group.group_id == group_id).all()

    data = []
    for acc_group in members:
        data.append(
            {
                "account_id": acc_group.belongs_user.id,
                "username": acc_group.belongs_user.username,
                "email": acc_group.belongs_user.email,
                "is_owner": acc_group.is_owner,
                "upload": acc_group.can_upload_dataset,
                "editable": acc_group.editable,
                "status": acc_group.status,
            }
        )
    return jsonify({"status": "ok", "data": data})


@crud.route("/view_groups", methods=["GET"])  # get all groups of this user
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

            data.append(
                {
                    "group_id": group_id,
                    "group_name": group_name,
                    "editable": editable,
                    "can_upload_dataset": can_upload_dataset,
                    "owner": is_owner,
                    "status": status,
                    "group_description": group_description,
                }
            )
        return jsonify({"status": "ok", "data": data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@crud.route("/view_all_groups", methods=["GET"])  # get all groups, only used by admin
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

# ------------------------------------------ Data CRUD --------------------------------------


@crud.route("/upload_data", methods=["POST"])
@token_required()
@permission_check(type='dataset', options='editable')
def upload():
    form_data = request.form
    Dataset_Data = json.loads(form_data.get("dataset_data"))

    Dataset_ID = Dataset_Data["dataset_id"]

    dataset = Dataset.query.filter_by(id=Dataset_ID).first()
    if dataset is None:
        abort(404, description="Dataset not found")

    files = []
    for key in request.files.keys():
        if key.startswith("file"):
            files.extend(request.files.getlist(key))

    if len(files) == 0:
        return "No files uploaded."

    for file in files:
        
        response = _upload_orthanc(file)
        print(response)
        
        if (response.status_code == 200):
            orthanc_data = json.loads(response.content)
            

            patient_pair = Dataset_Patients.query.filter(
                and_(
                    Dataset_Patients.patient_orthanc_id == orthanc_data["ParentPatient"],
                    Dataset_Patients.dataset_id == Dataset_ID,
                )
            ).first()
            if patient_pair is None:
                _new_patient_pair(orthanc_data, Dataset_ID)
            else:
                patient_pair.valid = True
                db.session.commit()

            study_pair = Dataset_Studies.query.filter(
                and_(
                    Dataset_Studies.patient_orthanc_id == orthanc_data["ParentPatient"],
                    Dataset_Studies.study_orthanc_id == orthanc_data["ParentStudy"],
                    Dataset_Studies.dataset_id == Dataset_ID,
                )
            ).first()
            if study_pair is None:
                _new_study_pair(orthanc_data, Dataset_ID)
            else:
                study_pair.valid = True
                db.session.commit()

            series_pair = Dataset_Series.query.filter(
                and_(
                    Dataset_Series.patient_orthanc_id == orthanc_data["ParentPatient"],
                    Dataset_Series.study_orthanc_id == orthanc_data["ParentStudy"],
                    Dataset_Series.series_orthanc_id == orthanc_data["ParentSeries"],
                    Dataset_Series.dataset_id == Dataset_ID,
                )
            ).first()
            if series_pair is None:
                _new_series_pair(orthanc_data, Dataset_ID)
            else:
                series_pair.valid = True
                db.session.commit()

            instance_pair = Dataset_Instances.query.filter(
                and_(
                    Dataset_Instances.series_orthanc_id == orthanc_data["ParentSeries"],
                    Dataset_Instances.instance_orthanc_id == orthanc_data["ID"]
                )
            ).first()
            if instance_pair is None:
                _new_instance_pair(orthanc_data)
            else:
                instance_pair.status = 0
                db.session.commit()

    return "Success upload"


def _upload_orthanc(file):
    upload_url = f"{orthanc_url}/instances"  # Orthanc的URL
    if not file or not file.filename:
        return "Empty filename."
    file_data = file.stream.read()
    response = requests.post(
        upload_url, data=file_data, headers={"Content-Type": "application/dicom"}
    )
        # print(response)
    return response


def _new_patient_pair(orthanc_data, Dataset_ID):
    patient_orthanc_ID = orthanc_data["ParentPatient"]

    patient_tags_url = f"{orthanc_url}/patients/{patient_orthanc_ID}/shared-tags?simplify"
    response = requests.get(patient_tags_url)
    # patient_info = json.loads(response.content)
    shared_tags = response.json()

    patient = Patient.query.filter_by(patient_orthanc_id=patient_orthanc_ID).first()
    if patient is None:
        # main_dicom_tags = patient_info.get("MainDicomTags", {})
        new_patient = Patient(
            patient_orthanc_id = patient_orthanc_ID,
            patient_id = shared_tags.get("PatientID", ""),
            patient_name = shared_tags.get("PatientName", ""),
            patient_sex = shared_tags.get("PatientSex", ""),
            patient_birthdate = shared_tags.get("PatientBirthDate", ""),
            patient_weight = shared_tags.get("PatientWeight", ""),
        )
        db.session.add(new_patient)
        db.session.commit()

    new_patient_pair = Dataset_Patients(
        patient_orthanc_id=patient_orthanc_ID,
        dataset_id=Dataset_ID,
    )
    db.session.add(new_patient_pair)
    db.session.commit()

    return 


def _new_study_pair(orthanc_data, Dataset_ID):
    patient_orthanc_ID = orthanc_data["ParentPatient"]
    study_orthanc_ID = orthanc_data["ParentStudy"]

    patient_pair = Dataset_Patients.query.filter(
        and_(
            Dataset_Patients.patient_orthanc_id == orthanc_data["ParentPatient"],
            Dataset_Patients.dataset_id == Dataset_ID,
        )
    ).first()
    if patient_pair is None:
        abort(404, description="Dataset and patient not match")

    study = Study.query.filter_by(study_orthanc_id=orthanc_data["ParentStudy"]).first()
    if study is None:
        _new_study(orthanc_data)
    else:
        study.valid = True
        db.session.commit()

    new_study_pair = Dataset_Studies(
        D_P_pair_id = patient_pair.D_P_pair_id,
        patient_orthanc_id = patient_orthanc_ID,
        study_orthanc_id = study_orthanc_ID,
        dataset_id = Dataset_ID,
    )
    db.session.add(new_study_pair)
    db.session.commit()

    return


def _new_study(orthanc_data):
    study_orthanc_id = orthanc_data["ParentStudy"]

    study_tags_url = f"{orthanc_url}/studies/{study_orthanc_id}"
    response = requests.get(study_tags_url)
    study_info = json.loads(response.content)

    main_dicom_tags = study_info.get("MainDicomTags", {})
    new_study = Study(
        study_orthanc_id=study_orthanc_id,
        study_instance_uid=main_dicom_tags.get("StudyInstanceUID", ""),
        study_date=main_dicom_tags.get("StudyDate", ""),
        study_time=main_dicom_tags.get("StudyTime", ""),
        study_id=main_dicom_tags.get("StudyID", ""),
        study_description=main_dicom_tags.get("StudyDescription", ""),
        accession_number=main_dicom_tags.get("AccessionNumber", ""),
        requested_procedure_description=main_dicom_tags.get(
            "RequestedProcedureDescription", ""
        ),
        institution_name=main_dicom_tags.get("InstitutionName", ""),
        requesting_physician=main_dicom_tags.get("RequestingPhysician", ""),
        referring_physician_name=main_dicom_tags.get("ReferringPhysicianName", ""),
    )
    db.session.add(new_study)
    db.session.commit()


def _new_series_pair(orthanc_data, Dataset_ID):
    patient_orthanc_ID = orthanc_data["ParentPatient"]
    study_orthanc_ID = orthanc_data["ParentStudy"]
    series_orthanc_ID = orthanc_data["ParentSeries"]

    study_pair = Dataset_Studies.query.filter(
        and_(
            Dataset_Studies.patient_orthanc_id == orthanc_data["ParentPatient"],
            Dataset_Studies.study_orthanc_id == orthanc_data["ParentStudy"],
            Dataset_Studies.dataset_id == Dataset_ID,
        )
    ).first()
    if study_pair is None:
        abort(404, description="Dataset-patient and study do not match")

    series = Series.query.filter_by(series_orthanc_id=orthanc_data["ParentSeries"]).first()
    if series is None:
        print("none series")
        _new_series(orthanc_data)
    else:
        series.valid = True
        db.session.commit()

    new_series_pair = Dataset_Series(
        DP_S_pair_id = study_pair.DP_S_pair_id,
        patient_orthanc_id=patient_orthanc_ID,
        study_orthanc_id=study_orthanc_ID,
        series_orthanc_id=series_orthanc_ID,
        dataset_id=Dataset_ID,
    )
    db.session.add(new_series_pair)
    db.session.commit()

    return


def _new_series(orthanc_data):
    series_orthanc_id = orthanc_data["ParentSeries"]

    series_tags_url = f"{orthanc_url}/series/{series_orthanc_id}"
    response = requests.get(series_tags_url)
    series_info = json.loads(response.content)

    main_dicom_tags = series_info.get("MainDicomTags", {})
    def safe_int(value):
        try:
            return int(value) if value else None
        except ValueError:
            return None

    new_series = Series(
        series_orthanc_id=series_orthanc_id,
        series_instance_uid=main_dicom_tags.get("SeriesInstanceUID", ""),
        series_date=main_dicom_tags.get("SeriesDate", ""),
        series_time=main_dicom_tags.get("SeriesTime", ""),
        modality=main_dicom_tags.get("Modality", ""),
        manufacturer=main_dicom_tags.get("Manufacturer", ""),
        station_name=main_dicom_tags.get("StationName", ""),
        series_description=main_dicom_tags.get("SeriesDescription", ""),
        body_part_examined=main_dicom_tags.get("BodyPartExamined", ""),
        sequence_name=main_dicom_tags.get("SequenceName", ""),
        protocol_name=main_dicom_tags.get("ProtocolName", ""),
        series_number=safe_int(main_dicom_tags.get("SeriesNumber")),
        cardiac_number_of_images=safe_int(main_dicom_tags.get("CardiacNumberOfImages")),
        images_in_acquisition=safe_int(main_dicom_tags.get("ImagesInAcquisition")),
        number_of_temporal_positions=safe_int(
            main_dicom_tags.get("NumberOfTemporalPositions")
        ),
        number_of_slices=safe_int(main_dicom_tags.get("NumberOfSlices")),
        number_of_time_slices=safe_int(main_dicom_tags.get("NumberOfTimeSlices")),
        image_orientation_patient=main_dicom_tags.get("ImageOrientationPatient", ""),
        series_type=main_dicom_tags.get("SeriesType", ""),
        operators_name=main_dicom_tags.get("OperatorsName", ""),
        performed_procedure_step_description=main_dicom_tags.get(
            "PerformedProcedureStepDescription", ""
        ),
        acquisition_device_processing_description=main_dicom_tags.get(
            "AcquisitionDeviceProcessingDescription", ""
        ),
        contrast_bolus_agent=main_dicom_tags.get("ContrastBolusAgent", ""),
    )
    db.session.add(new_series)
    db.session.commit()
    print(f"Successfully added series with ID: {new_series.series_orthanc_id}")


def _new_instance_pair(orthanc_data):
    series_orthanc_ID = orthanc_data["ParentSeries"]
    instance_orthanc_ID = orthanc_data["ID"]

    new_instance_pair = Dataset_Instances(
        series_orthanc_id=series_orthanc_ID,
        instance_orthanc_id=instance_orthanc_ID,
        status=0,
    )
    db.session.add(new_instance_pair)
    db.session.commit()

    return


@crud.route("/view_patient_by_dataset", methods=["GET"])
@token_required()
def search_Patient():

    dataset_id = request.args['dataset_id']

    dataset_patients = Dataset_Patients.query.filter(
        Dataset_Patients.dataset_id == dataset_id
    ).all()
    if dataset_patients is None:
        abort(404, description="No patient was found")

    patient_list = []
    for patient in dataset_patients:
        if (patient.valid):
            patient_list.append(patient.patient_orthanc_id)

    # patient_orthanc_ids = Patient.query.filter(Patient.valid == True).all()
    # patient_list = [p.patient_orthanc_id for p in patient_orthanc_ids]

    patients = Patient.query.filter(Patient.patient_orthanc_id.in_(patient_list)).all()
    patient_dict = []
    for patient in patients:
        patient_dict.append({
            "patient_orthanc_id":patient.patient_orthanc_id,
            "PatientName":patient.patient_name,
            "PatientID":patient.patient_id,
            "PatientBirthDate":patient.patient_birthdate,
            "PatientSex":patient.patient_sex,
        })
    return jsonify(patient_dict)


@crud.route("/view_study_by_patient", methods=["GET"])
@token_required()
def search_study():
 
    dataset_id = request.args['dataset_id']
    patient_id = request.args["patient_id"]

    study_pair = Dataset_Studies.query.filter(
        and_(
            Dataset_Studies.patient_orthanc_id == patient_id,
            Dataset_Studies.dataset_id == dataset_id,
        )
    ).all()
    if study_pair is None:
        abort(404, description="No study was found")

    study_dict = []
    for study in study_pair:
        if (study.valid):
            info = _get_study_info(study.study_orthanc_id)
            study_dict.append(info)

    return jsonify(study_dict)

def _get_study_info(study_orthanc_id):
    Study_url = f"{orthanc_url}/studies/{study_orthanc_id}?=short"

    response = requests.get(Study_url)

    if response.status_code == 200:

        studies_info = response.json()
        main_dicom_tags = studies_info.get("MainDicomTags", {})

        # study_Description = studies_info["MainDicomTags"]["StudyDescription"]
        # study_Date = studies_info["MainDicomTags"]["StudyDate"]
        # study_InstanceUID = studies_info["MainDicomTags"]["StudyInstanceUID"]
        # study_Accessnumber = studies_info["MainDicomTags"]["AccessionNumber"]

        study_dict = {
            "StudyDescription": main_dicom_tags.get("StudyDescription", ""),
            "StudyDate": main_dicom_tags.get("StudyDate", ""),
            "study_orthanc_id": study_orthanc_id,
            "StudyInstanceUID": main_dicom_tags.get("StudyInstanceUID", ""),
            "AccessionNumber": main_dicom_tags.get("AccessionNumber", ""),
        }

    return study_dict


@crud.route("/view_series_by_study", methods=["GET"])
@token_required()
def search_series():

    dataset_id = request.args["dataset_id"]
    patient_id = request.args["patient_id"]
    study_id = request.args["study_id"]

    series_pair = Dataset_Series.query.filter(
        and_(
            Dataset_Series.patient_orthanc_id == patient_id,
            Dataset_Series.study_orthanc_id == study_id,
            Dataset_Series.dataset_id == dataset_id,
        )
    ).all()
    if series_pair is None:
        abort(404, description="No series was found")

    series_dict = []
    for series in series_pair:
        if series.valid:
            info = _get_series_info(series.series_orthanc_id)
            series_dict.append(info)
    return jsonify(series_dict)

def _get_series_info(series_orthanc_id):

    serie_url = f"{orthanc_url}/series/{series_orthanc_id}?=short"
    series_response = requests.get(serie_url)
    if series_response.status_code == 200:
        series_info = series_response.json()
        main_dicom_tags = series_info.get("MainDicomTags", {})
        # series_Modality = series_info["MainDicomTags"]["Modality"]
        # series_SeriesInstanceUID = series_info["MainDicomTags"]["SeriesInstanceUID"]
        # series_SeriesNumber = series_info["MainDicomTags"]["SeriesNumber"]
        # series_ProtocolName = series_info["MainDicomTags"]["ProtocolName"]

        series_dict = {
            "series_orthanc_id": series_orthanc_id,
            "Modality": main_dicom_tags.get("Modality", ""),
            "SeriesNumber": main_dicom_tags.get("SeriesNumber", ""),
            "SeriesInstanceUID": main_dicom_tags.get("SeriesInstanceUID", ""),
            "ProtocolName": main_dicom_tags.get("ProtocolName", ""),
        }

    return series_dict


@crud.route("/view_instances_by_series", methods=["GET"])
@token_required()
def search_instances():

    series_orthanc_id = request.args['series_orthanc_id']

    instance_pair = Dataset_Instances.query.filter(
        Dataset_Instances.series_orthanc_id == series_orthanc_id
    ).all()
    if instance_pair is None:
        abort(404, description="No instance was found")

    instance_dict = []
    for instance in instance_pair:
        if (instance.status == 0):
            info = _get_instance_info(instance.instance_orthanc_id)
            instance_dict.append(info)

    return jsonify(instance_dict)


def _get_instance_info(instance_orthanc_id):

    instance_url = f"{orthanc_url}/instances/{instance_orthanc_id}?=short"
    instance_response = requests.get(instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()

        instance_dict = {
            "instance_orthanc_id": instance_orthanc_id,
            "SOPInstanceUID": instance_info["MainDicomTags"]["SOPInstanceUID"],
        }

    return instance_dict


@crud.route("/delete-files", methods=["DELETE"])
@token_required()
@permission_check(type="dataset", options="editable")
def deletefiles():
    file_data = request.get_json()
    Dataset_ID = file_data["dataset_id"]
    dataset_structure_list = file_data["file_dict"]

    initial_items = [
        (item_id, path[-1]["class"]) for item_id, path in dataset_structure_list.items()
    ]

    to_delete, item_class_dict = process_deletions(initial_items, Dataset_ID)

    delete_files_list = defaultdict(list)
    for item_id in to_delete:
        item_class = item_class_dict[item_id]
        delete_files_list[item_class].append(item_id)

    update_database(delete_files_list, Dataset_ID)

    return jsonify(f"Successfully deleted {len(to_delete)} files!")


def get_orthanc_id_field(class_name):
    if class_name == "Instances":
        return "instance_orthanc_id"
    return f"{class_name.lower()}_orthanc_id"


def process_deletions(initial_items, Dataset_ID):
    to_delete = set(item_id for item_id, _ in initial_items)
    item_class_dict = {item_id: item_class for item_id, item_class in initial_items}

    items_to_process = list(to_delete)
    while items_to_process:
        item_id = items_to_process.pop(0)
        item_class = item_class_dict[item_id]

        current_id = item_id
        current_class = item_class
        while current_class != "Patient":
            parent_id = get_parent(current_id, current_class, Dataset_ID)
            if parent_id is None:
                break
            parent_class = get_parent_class(current_class)
            siblings = get_children(parent_id, parent_class, Dataset_ID)
            orthanc_id_field = get_orthanc_id_field(current_class)
            if all(
                getattr(sibling, orthanc_id_field) in to_delete
                for sibling in siblings
            ):
                to_delete.add(parent_id)
                if parent_id not in item_class_dict:
                    item_class_dict[parent_id] = parent_class
                    items_to_process.append(parent_id)
            current_id = parent_id
            current_class = parent_class

        children_stack = [(item_id, item_class)]
        while children_stack:
            current_id, current_class = children_stack.pop()
            children = get_children(current_id, current_class, Dataset_ID)
            child_class = get_child_class(current_class)
            if child_class:
                for child in children:
                    orthanc_id_field = get_orthanc_id_field(child_class)
                    child_id = getattr(child, orthanc_id_field)
                    if child_id not in to_delete:
                        to_delete.add(child_id)
                        item_class_dict[child_id] = child_class
                        if child_class != "Instances":
                            children_stack.append((child_id, child_class))

    return to_delete, item_class_dict


def get_children(item_id, item_class, Dataset_ID):
    if item_class == "Patient":
        return Dataset_Studies.query.filter_by(
            dataset_id=Dataset_ID, patient_orthanc_id=item_id, valid=True
        ).all()
    elif item_class == "Study":
        return Dataset_Series.query.filter_by(
            dataset_id=Dataset_ID, study_orthanc_id=item_id, valid=True
        ).all()
    elif item_class == "Series":
        return Dataset_Instances.query.filter_by(
            series_orthanc_id=item_id, status=0
        ).all()
    return []


def get_parent(item_id, item_class, Dataset_ID):
    if item_class == "Study":
        study = Dataset_Studies.query.filter_by(
            study_orthanc_id=item_id, dataset_id=Dataset_ID
        ).first()
        return study.patient_orthanc_id if study else None
    elif item_class == "Series":
        series = Dataset_Series.query.filter_by(
            series_orthanc_id=item_id, dataset_id=Dataset_ID
        ).first()
        return series.study_orthanc_id if series else None
    elif item_class == "Instances":
        instance = Dataset_Instances.query.filter_by(
            instance_orthanc_id=item_id
        ).first()
        return instance.series_orthanc_id if instance else None
    return None


def update_database(delete_files_list, Dataset_ID):
    for class_name, id_list in delete_files_list.items():
        if class_name == "Patient":
            Dataset_Patients.query.filter(
                Dataset_Patients.patient_orthanc_id.in_(id_list),
                Dataset_Patients.dataset_id == Dataset_ID,
            ).update({Dataset_Patients.valid: False}, synchronize_session="fetch")
        elif class_name == "Study":
            Dataset_Studies.query.filter(
                Dataset_Studies.study_orthanc_id.in_(id_list),
                Dataset_Studies.dataset_id == Dataset_ID,
            ).update({Dataset_Studies.valid: False}, synchronize_session="fetch")
        elif class_name == "Series":
            Dataset_Series.query.filter(
                Dataset_Series.series_orthanc_id.in_(id_list),
                Dataset_Series.dataset_id == Dataset_ID,
            ).update({Dataset_Series.valid: False}, synchronize_session="fetch")
        elif class_name == "Instances":
            Dataset_Instances.query.filter(
                Dataset_Instances.instance_orthanc_id.in_(id_list)
            ).update({Dataset_Instances.status: 1}, synchronize_session="fetch")
    db.session.commit()


HIERARCHY = {
    "forward": {"Patient": "Study", "Study": "Series", "Series": "Instances"},
    "reverse": {"Study": "Patient", "Series": "Study", "Instances": "Series"},
}


def get_child_class(parent_class):
    return HIERARCHY["forward"].get(parent_class)


def get_parent_class(child_class):
    return HIERARCHY["reverse"].get(child_class)


@crud.route("/get_maintag_info", methods=["GET"])
def get_maintag_info():

    Orthanc_id = request.args["id"]
    info_class = request.args["class"]
    
    if info_class == "Study":
        result_dict =  _get_study_taginfo(Orthanc_id)
    elif info_class == "Series":
        result_dict =  _get_series_taginfo(Orthanc_id)
    elif info_class == "Instances":
        result_dict =  _get_instance_taginfo(Orthanc_id)
    else:
        abort(400, description="Invalid 'class' parameter")

    if result_dict is None:
        abort(404, description=f"No data found for {info_class} with ID {Orthanc_id}")


    return result_dict


def _get_study_taginfo(study_orthanc_id):
    Study_url = f"{orthanc_url}/studies/{study_orthanc_id}?=full"

    response = requests.get(Study_url)

    if response.status_code == 200:

        studies_info = response.json()
        main_dicom_tags = studies_info.get("MainDicomTags", {})

    else:
        return None

    return main_dicom_tags


def _get_series_taginfo(series_orthanc_id):

    serie_url = f"{orthanc_url}/series/{series_orthanc_id}?=full"
    series_response = requests.get(serie_url)
    if series_response.status_code == 200:
        series_info = series_response.json()
        main_dicom_tags = series_info.get("MainDicomTags", {})

    else:
        return None

    return main_dicom_tags


def _get_instance_taginfo(instance_orthanc_id):

    instance_url = f"{orthanc_url}/instances/{instance_orthanc_id}?=full"
    instance_response = requests.get(instance_url)
    if instance_response.status_code == 200:
        instance_info = instance_response.json()
        main_dicom_tags = instance_info.get("MainDicomTags", {})

    else:
        return None

    return main_dicom_tags


@crud.route('/get_Instance', methods=['GET'])
@token_required()
def get_instance():
    try:
        instance_id = request.args.get('oid')
        if not instance_id:
            return {'error': 'Instance ID is required'}, 400

        orthanc_instance_url = f"{orthanc_url}/instances/{instance_id}/file"
        
        response = requests.get(
            orthanc_instance_url,
            stream=True
        )
        
        if response.status_code != 200:
            return {
                'error': f'Failed to fetch instance from Orthanc. Status code: {response.status_code}'
            }, response.status_code

        file_path = os.path.join(r"E:\Cloud-Platform\Metaset-Quant Backend\ComfyUI\test_cache\tmp", f'instance_{instance_id}.dcm')

        with open(file_path, 'wb') as f:
            f.write(response.content)

        
        # try:
            response = make_response(send_file(file_path, mimetype="application/dicom"))
            return response
        # finally:
        #     # 在发送后清理临时文件
        #     def cleanup():
        #         try:
        #             if os.path.exists(file_path):
        #                 os.remove(file_path)
        #         except Exception as e:
        #             print(f"Error cleaning up temporary file: {e}")
            
        #     # 使用 after_this_request 确保文件被发送后再删除
        #     @after_this_request
        #     def remove_file(response):
        #         cleanup()
        #         return response

    except requests.RequestException as e:
        return {'error': f'Network error: {str(e)}'}, 500
    except Exception as e:
        return {'error': f'Server error: {str(e)}'}, 500
