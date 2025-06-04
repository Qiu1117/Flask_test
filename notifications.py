from flask import jsonify, request, g
from middleware import token_required
import json
import shortuuid
from db_models import db, Account, Group, Acc_Group
from sqlalchemy import text

# Don't create separate blueprint, these will be registered in crud_main.py

def get_notifications():
    acc_id = g.account_id
    notifications = Account.query.filter_by(id=acc_id).first().notification
    return jsonify({"status": "ok", "data": notifications})

def process_group_invi():
    data = request.get_json()
    accept = data["accept"]
    group_id = data["group_id"]
    note_id = data["note_id"]

    if accept:
        acc_group_map = Acc_Group.query.filter_by(
            acc_id=g.account_id, group_id=group_id
        ).first()
        acc_group_map.status = 0

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
        return jsonify({"status": "error", "message": "The notification not belong to you!"}), 500

def invit_acc_to_group():
    data = request.get_json()
    acc_id = data["account_id"]
    group_id = data["group_id"]

    group = Group.query.filter_by(id=group_id).first()
    if group is None:
        return jsonify({"status": "error", "message": "Group not found"}), 404
        
    exist_pair = Acc_Group.query.filter_by(
        group_id=data["group_id"], acc_id=acc_id
    ).first()
    
    if exist_pair:
        if exist_pair.status == 0:
            return jsonify({"status": "error", "message": "Group already exist"}), 404
        elif exist_pair.status == 1:
            return jsonify({"status": "error", "message": "Invitation already sent"}), 404
        elif exist_pair.status == 2:
            exist_pair.status = 1
            db.session.commit()
            return jsonify({"status": "ok"})
    else:
        acc_group_map = Acc_Group(
            acc_id=acc_id,
            group_id=group_id,
            editable=False,
            can_upload_dataset=False,
            is_owner=False,
            status=1,
        )
        db.session.add(acc_group_map)

        uid = shortuuid.uuid()
        note = {
            uid: {
                "message": f"User: {g.account_id} invite you to Group: {group.group_name}",
                "response_route": "/accept_group_invi",
                "content": {"group_id": group_id},
                "status": 0,
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

def send_message():
    data = request.get_json()
    target_users = data["target_users"]
    message = data["message"]

    _send_message(message, target_users)
    return jsonify({"status": "ok"})

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
        return jsonify({"status": "error", "message": "The notification not belong to you!"}), 500

def _send_message(message, target_users):
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
    db.session.commit()