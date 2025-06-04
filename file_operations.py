from flask import jsonify, request, Blueprint, make_response, send_file, abort
from middleware import token_required, permission_check
from collections import defaultdict
from sqlalchemy import and_
from db_models import (
    db, Dataset_Patients, Dataset_Studies, Dataset_Series, Dataset_Instances
)
from orthanc_utils import orthanc_request
import os
import requests

file_operations = Blueprint("file_operations", __name__)

@file_operations.route("/delete-files", methods=["DELETE"])
@token_required()
@permission_check(type="dataset", options="editable")
def deletefiles():
    file_data = request.get_json()
    dataset_id = file_data["dataset_id"]
    dataset_structure_list = file_data["file_dict"]

    initial_items = [
        (item_id, path[-1]["class"]) for item_id, path in dataset_structure_list.items()
    ]

    to_delete, item_class_dict = process_deletions(initial_items, dataset_id)

    delete_files_list = defaultdict(list)
    for item_id in to_delete:
        item_class = item_class_dict[item_id]
        delete_files_list[item_class].append(item_id)

    update_database(delete_files_list, dataset_id)

    return jsonify(f"Successfully deleted {len(to_delete)} files!")


@file_operations.route('/get_Instance', methods=['GET'])
@token_required()
def get_instance():
    try:
        instance_id = request.args.get('oid')
        if not instance_id:
            return jsonify({'error': 'Instance ID is required'}), 400

        orthanc_instance_url = f"instances/{instance_id}/file"
        
        response = orthanc_request("GET", orthanc_instance_url, stream=True)
        
        if response.status_code != 200:
            return jsonify({
                'error': f'Failed to fetch instance from Orthanc. Status code: {response.status_code}'
            }), response.status_code

        temp_dir = os.path.join("tmp")
        os.makedirs(temp_dir, exist_ok=True)
        
        file_path = os.path.join(temp_dir, f'instance_{instance_id}.dcm')

        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        response = make_response(send_file(file_path, mimetype="application/dicom"))
        return response

    except requests.RequestException as e:
        return jsonify({'error': f'Network error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


def get_orthanc_id_field(class_name):
    if class_name == "Instances":
        return "instance_orthanc_id"
    return f"{class_name.lower()}_orthanc_id"


def process_deletions(initial_items, dataset_id):
    to_delete = set(item_id for item_id, _ in initial_items)
    item_class_dict = {item_id: item_class for item_id, item_class in initial_items}

    items_to_process = list(to_delete)
    while items_to_process:
        item_id = items_to_process.pop(0)
        item_class = item_class_dict[item_id]

        current_id = item_id
        current_class = item_class
        while current_class != "Patient":
            parent_id = get_parent(current_id, current_class, dataset_id)
            if parent_id is None:
                break
            parent_class = get_parent_class(current_class)
            siblings = get_children(parent_id, parent_class, dataset_id)
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
            children = get_children(current_id, current_class, dataset_id)
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


def get_children(item_id, item_class, dataset_id):
    if item_class == "Patient":
        return Dataset_Studies.query.filter_by(
            dataset_id=dataset_id, patient_orthanc_id=item_id, valid=True
        ).all()
    elif item_class == "Study":
        return Dataset_Series.query.filter_by(
            dataset_id=dataset_id, study_orthanc_id=item_id, valid=True
        ).all()
    elif item_class == "Series":
        return Dataset_Instances.query.filter_by(
            series_orthanc_id=item_id, status=0
        ).all()
    return []


def get_parent(item_id, item_class, dataset_id):
    if item_class == "Study":
        study = Dataset_Studies.query.filter_by(
            study_orthanc_id=item_id, dataset_id=dataset_id
        ).first()
        return study.patient_orthanc_id if study else None
    elif item_class == "Series":
        series = Dataset_Series.query.filter_by(
            series_orthanc_id=item_id, dataset_id=dataset_id
        ).first()
        return series.study_orthanc_id if series else None
    elif item_class == "Instances":
        instance = Dataset_Instances.query.filter_by(
            instance_orthanc_id=item_id
        ).first()
        return instance.series_orthanc_id if instance else None
    return None


def update_database(delete_files_list, dataset_id):
    for class_name, id_list in delete_files_list.items():
        if class_name == "Patient":
            Dataset_Patients.query.filter(
                Dataset_Patients.patient_orthanc_id.in_(id_list),
                Dataset_Patients.dataset_id == dataset_id,
            ).update({Dataset_Patients.valid: False}, synchronize_session="fetch")
        elif class_name == "Study":
            Dataset_Studies.query.filter(
                Dataset_Studies.study_orthanc_id.in_(id_list),
                Dataset_Studies.dataset_id == dataset_id,
            ).update({Dataset_Studies.valid: False}, synchronize_session="fetch")
        elif class_name == "Series":
            Dataset_Series.query.filter(
                Dataset_Series.series_orthanc_id.in_(id_list),
                Dataset_Series.dataset_id == dataset_id,
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