from flask import Blueprint
from middleware import token_required, permission_check

# Import all functions
from notifications import *
from datasets import *
from accounts import *
from groups import *
from data_views import *
from file_operations import *
from upload_routes import *

crud = Blueprint("crud", __name__)

# Register all original routes with original paths and function names

# Notification routes
@crud.route("/get_notifications", methods=["GET"])
@token_required()
def get_notifications_route():
    return get_notifications()

@crud.route("/process_group_invi", methods=["POST"])
@token_required()
def process_group_invi_route():
    return process_group_invi()

@crud.route("/invite_acc_to_group", methods=["POST"])
@token_required()
def invit_acc_to_group_route():
    return invit_acc_to_group()

@crud.route("/send_message", methods=["POST"])
@token_required()
def send_message_route():
    return send_message()

@crud.route("/read_message", methods=["POST"])
@token_required()
def read_message_route():
    return read_message()

# Dataset routes
@crud.route("/create_dataset", methods=["POST"])
@token_required()
def create_dataset_route():
    return create_dataset()

@crud.route("/add_dataset_to_groups", methods=["POST"])
@token_required()
@permission_check(type="either", options="upload")
def add_groups_to_dataset_route():
    return add_groups_to_dataset()

@crud.route("/delete_dataset", methods=["DELETE"])
@token_required()
def delete_dataset_route():
    return delete_dataset()

@crud.route("/remove_dataset_from_group", methods=["DELETE"])
@token_required()
@permission_check(type="dataset")
def remove_dataset_from_group_route():
    return remove_dataset_from_group()

@crud.route("/recover_dataset", methods=["POST"])
@token_required()
def recover_dataset_route():
    return recover_dataset()

@crud.route("/update_dataset", methods=["POST"])
@token_required()
@permission_check(type="either", options="editable")
def update_dataset_route():
    return update_dataset()

@crud.route("/view_groups_from_dataset", methods=["GET"])
@token_required()
def view_groups_from_dataset_route():
    return view_groups_from_dataset()

@crud.route("/view_datasets_from_account", methods=["GET"])
@token_required()
def view_datasets_from_account_route():
    return view_datasets_from_account()

@crud.route("/view_all_datasets", methods=["GET"])
@token_required()
def view_all_datasets_route():
    return view_all_datasets()

# Account routes
@crud.route("/get_accounts", methods=["GET"])
@token_required()
def get_accounts_route():
    return get_accounts()

@crud.route("/get_account_info", methods=["GET"])
@token_required()
def get_account_info_route():
    return get_account_info()

@crud.route("/exit_group", methods=["POST"])
@token_required()
def exit_group_route():
    return exit_group()

# Group routes
@crud.route("/create_group", methods=["POST"])
@token_required()
def create_group_route():
    return create_group()

@crud.route("/delete_group", methods=["DELETE"])
@token_required()
def delete_group_route():
    return delete_group()

@crud.route("/delete_members_from_group", methods=["DELETE"])
@token_required()
@permission_check(type="group", options="editable")
def delete_members_from_group_route():
    return delete_members_from_group()

@crud.route("/recover_group", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def recover_group_route():
    return recover_group()

@crud.route("/recover_group_members", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def recover_group_members_route():
    return recover_group_members()

@crud.route("/update_group_info", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def update_group_info_route():
    return update_group_info()

@crud.route("/update_group_rights", methods=["POST"])
@token_required()
@permission_check(type="group", options="editable")
def update_group_rights_route():
    return update_group_rights()

@crud.route("/view_members_from_group", methods=["GET"])
@token_required()
def view_members_from_group_route():
    return view_members_from_group()

@crud.route("/view_groups", methods=["GET"])
@token_required()
def view_groups_route():
    return view_groups()

@crud.route("/view_all_groups", methods=["GET"])
@token_required(check_admin=True)
def view_all_groups_route():
    return view_all_groups()

# Data view routes
@crud.route("/view_patient_by_dataset", methods=["GET"])
@token_required()
def search_Patient_route():
    return search_Patient()

@crud.route("/view_study_by_patient", methods=["GET"])
@token_required()
def search_study_route():
    return search_study()

@crud.route("/view_series_by_study", methods=["GET"])
@token_required()
def search_series_route():
    return search_series()

@crud.route("/view_instances_by_series", methods=["GET"])
@token_required()
def search_instances_route():
    return search_instances()

@crud.route("/get_maintag_info", methods=["GET"])
def get_maintag_info_route():
    return get_maintag_info()

# File operation routes
@crud.route("/delete-files", methods=["DELETE"])
@token_required()
@permission_check(type="dataset", options="editable")
def deletefiles_route():
    return deletefiles()

@crud.route('/get_Instance', methods=['GET'])
@token_required()
def get_instance_route():
    return get_instance()

# Upload routes
@crud.route("/upload_data", methods=["POST"])
@token_required()
@permission_check(type='dataset', options='editable')
def upload_route():
    return upload()

@crud.route("/upload_archive", methods=["POST"])
@token_required()
@permission_check(type='dataset', options='editable')
def upload_archive_route():
    return upload_archive()