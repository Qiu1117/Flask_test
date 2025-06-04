from flask import jsonify, request, Blueprint, abort, g
from middleware import token_required, permission_check
from sqlalchemy import and_, or_
from db_models import (
    db, Account, Group, Acc_Group, Dataset_Group, Dataset
)
from notifications import _send_message

datasets = Blueprint("datasets", __name__)

@datasets.route("/create_dataset", methods=["POST"])
@token_required()
def create_dataset():
    data = request.get_json()
    dataset_info = data.get("dataset_info", {})
    dataset_owner = data.get("dataset_owner")

    dataset_name = dataset_info.get("dataset_name", "anonymous")
    default_group_name = f"default_{dataset_name}"
    default_group = Group(
        group_name=default_group_name,
        description=f"This is a default group for dataset {dataset_name}",
        owner=dataset_owner,
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


@datasets.route("/add_dataset_to_groups", methods=["POST"])
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
                
    operation_group_id = [x for x in group_ids if x not in exist_group_id]
    for group_id in operation_group_id:
        new_data_group = Dataset_Group(group_id=group_id, dataset_id=dataset_id)
        db.session.add(new_data_group)

    db.session.commit()

    member_list = get_members_from_groups(group_ids, False)
    target_dataset = Dataset.query.filter_by(id=dataset_id).first()
    message = f"The dataset: {target_dataset.dataset_name} has been added to your group."
    if len(member_list) != 0:
        _send_message(message, member_list)

    if err:
        return jsonify({
            "status": "warning",
            "message": f"Group {' '.join(err)} have been on the dataset",
        })
    else:
        return jsonify({"status": "ok"})


@datasets.route("/delete_dataset", methods=["DELETE"])
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


@datasets.route("/remove_dataset_from_group", methods=["DELETE"])
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

    exist_pairs = Dataset_Group.query.filter(
        and_(
            Dataset_Group.dataset_id == dataset_id,
            Dataset_Group.group_id.in_(group_ids),
        )
    ).all()
    exist_group_id = [x.group_id for x in exist_pairs]
    
    if exist_pairs:
        for i in exist_pairs:
            if i.valid:
                i.valid = False
            else:
                db.session.delete(i)

            target_group = Group.query.filter(Group.id == i.group_id).first()
            members = target_group.owner
            target_dataset = Dataset.query.filter_by(id=dataset_id).first()
            message = f"Your group: {target_group.group_name} has been removed from dataset: {target_dataset.dataset_name}."
            if len([members]) != 0:
                _send_message(message, [members])

        db.session.commit()

        err = [x for x in group_ids if x not in exist_group_id]
        if err:
            return jsonify({
                "status": "warning",
                "message": f"Group {' '.join(str(e) for e in err)} have been on the dataset",
            })
        else:
            return jsonify({"status": "ok"})
    else:
        abort(404, "None of the given id pairs are exist")


@datasets.route("/recover_dataset", methods=["POST"])
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


@datasets.route("/update_dataset", methods=["POST"])
@token_required()
@permission_check(type="either", options="editable")
def update_dataset():
    data = request.get_json()
    dataset_info = data.get("dataset_info", {})
    dataset_id = data.get("dataset_id")
    dataset = Dataset.query.filter_by(id=dataset_id).first()
    if dataset is None:
        abort(404, description="Dataset not found")

    for key, value in dataset_info.items():
        if value is not None and value != "":
            setattr(dataset, key, value)

    db.session.commit()

    members = dataset.owner
    message = f"Your dataset: {dataset.dataset_name} has been updated."
    if len([members]) != 0:
        _send_message(message, [members])
    return jsonify({"status": "ok"})


@datasets.route("/view_groups_from_dataset", methods=["GET"])
@token_required()
def view_groups_from_dataset():
    dataset_id = request.args["dataset_id"]
    dataset_groups = Dataset_Group.query.filter(
        Dataset_Group.dataset_id == dataset_id
    ).all()
    if dataset_groups is None:
        abort(404, description="No group was found")

    data = []
    for dataset_group in dataset_groups:
        data.append({
            "group_id": dataset_group.group_id,
            "name": dataset_group.belongs.group_name,
            "description": dataset_group.belongs.description,
            "group_valid": dataset_group.belongs.valid,
            "dataset_group_valid": dataset_group.valid,
        })
    return jsonify({"status": "ok", "data": data})


@datasets.route("/view_datasets_from_account", methods=["GET"])
@token_required()
def view_datasets_from_account():
    given_id = request.args.get("account_id")
    acc_id = given_id if given_id else g.account_id
    data = get_accessible_datasets_from_account(acc_id)
    return jsonify({"status": "ok", "data": data})


@datasets.route("/view_all_datasets", methods=["GET"])
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


def get_members_from_groups(group_ids, verbose=False):
    member_info = []
    members = (
        db.session.query(Account, Acc_Group)
        .join(Acc_Group)
        .filter(Acc_Group.group_id.in_(group_ids))
        .all()
    )

    if verbose:
        for account, acc_group in members:
            member_info.append({
                "id": account.id,
                "username": account.username,
                "email": account.email,
                "group_id": acc_group.group_id,
                "is_owner": acc_group.is_owner,
                "editable": acc_group.editable,
                "can_upload_dataset": acc_group.can_upload_dataset,
                "status": acc_group.status,
            })
    else:
        for account, acc_group in members:
            member_info.append(account.id)
    return member_info


def get_accessible_datasets_from_account(account_id):
    data = []
    seen_datasets = set()
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
        if dataset.id in seen_datasets:
            continue
        seen_datasets.add(dataset.id)
        owner = int(account_id) if str(dataset.owner) == str(account_id) else 0
        editable = True if owner else acc_group.editable
        can_upload_dataset = True if owner else acc_group.can_upload_dataset

        data.append({
            "group_id": None if owner else group.id,
            "group_name": None if owner else group.group_name,
            "dataset_id": dataset.id,
            "dataset_name": dataset.dataset_name,
            "valid": dataset.valid,
            "owner": owner,
            "editable": editable,
            "can_upload_dataset": can_upload_dataset,
        })
    return data