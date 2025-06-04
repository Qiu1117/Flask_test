from flask import jsonify, request, Blueprint
from middleware import token_required, permission_check
import json
import base64
import io
import os
from Encryption import decrypt_file
from upload_manager import (
    create_dataset_directory, create_upload_directory, save_uploaded_files,
    extract_archive_file_to_upload_dir, validate_dicom_file, 
    upload_dicom_to_orthanc, process_upload_request
)
from orthanc_utils import _upload_orthanc
from data_manager import update_database_records
from db_models import Dataset

upload_routes = Blueprint("upload_routes", __name__)

@upload_routes.route("/upload_data", methods=["POST"])
@token_required()
@permission_check(type='dataset', options='editable')
def upload():
    try:
        dataset_id, dataset, files, encryption_info, error = process_upload_request()
        if error:
            return jsonify({
                "error": error, 
                "success_count": 0, 
                "failed_count": 0, 
                "failed_files": []
            }), 400
        
        is_encrypted, aes_key, form_data = encryption_info
        
        dataset_dir = create_dataset_directory(dataset_id, dataset.dataset_name)
        upload_dir = create_upload_directory(dataset_dir)
        
        save_uploaded_files(files, upload_dir, is_encrypted, aes_key, form_data)
        
        success_count = 0
        failed_files = []
        
        for i, file in enumerate(files):
            try:
                file_content = file.read()
                
                if is_encrypted:
                    file_index = i
                    iv_key = f"iv_{file_index}"
                    
                    if iv_key not in form_data:
                        failed_files.append({
                            "file": file.filename, 
                            "error": f"Cannot find IV for file {i}"
                        })
                        continue
                    
                    iv = base64.b64decode(form_data.get(iv_key))
                    decrypted_content = decrypt_file(file_content, iv, aes_key)
                    
                    temp_file = io.BytesIO(decrypted_content)
                    temp_file.name = file.filename
                else:
                    file.seek(0)
                    temp_file = file
                
                response = _upload_orthanc(temp_file)
                
                if isinstance(response, dict):
                    failed_files.append({
                        "file": file.filename, 
                        "error": response.get("message", "Unknown error during upload")
                    })
                    continue
                
                if response.status_code != 200:
                    error_message = response.content.decode('utf-8') if hasattr(response, 'content') else "Unknown error"
                    failed_files.append({
                        "file": file.filename, 
                        "error": f"HTTP {response.status_code}: {error_message}"
                    })
                    continue
                
                orthanc_data = json.loads(response.content)
                
                db_success, db_error = update_database_records(orthanc_data, dataset_id)
                if not db_success:
                    failed_files.append({
                        "file": file.filename, 
                        "error": db_error
                    })
                    continue
                
                success_count += 1
                
            except Exception as file_error:
                failed_files.append({
                    "file": file.filename, 
                    "error": str(file_error)
                })
        
        return jsonify({
            "message": f"Upload completed: {success_count} successful, {len(failed_files)} failed",
            "success": True,
            "success_count": success_count,
            "failed_count": len(failed_files),
            "failed_files": failed_files,
            "upload_directory": upload_dir
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": "Failed to upload files", 
            "message": str(e),
            "success_count": 0,
            "failed_count": len(request.files) if request.files else 0,
            "failed_files": [{"file": "batch", "error": str(e)}]
        }), 500


@upload_routes.route("/upload_archive", methods=["POST"])
@token_required()
@permission_check(type='dataset', options='editable')
def upload_archive():
    try:
        if 'archivefile' not in request.files:
            return jsonify({
                "error": "No archive file found in request",
                "success_count": 0, 
                "failed_count": 0,
                "extracted_files": 0
            }), 400
        
        archive_file = request.files['archivefile']
        
        # Check supported archive formats
        supported_extensions = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz']
        file_extension = None
        for ext in supported_extensions:
            if archive_file.filename.lower().endswith(ext):
                file_extension = ext
                break
        
        if not file_extension:
            return jsonify({
                "error": "File must be a supported archive format (zip, rar, 7z, tar, gz, bz2, xz)",
                "success_count": 0,
                "failed_count": 0,
                "extracted_files": 0
            }), 400
            
        dataset_data = json.loads(request.form.get("dataset_data", "{}"))
        dataset_id = dataset_data.get("dataset_id")
        
        if not dataset_id:
            return jsonify({
                "error": "Missing dataset ID",
                "success_count": 0,
                "failed_count": 0,
                "extracted_files": 0
            }), 400
        
        dataset = Dataset.query.filter_by(id=dataset_id).first()
        if dataset is None:
            return jsonify({
                "error": "Dataset not found",
                "success_count": 0,
                "failed_count": 0,
                "extracted_files": 0
            }), 404
        
        dataset_dir = create_dataset_directory(dataset_id, dataset.dataset_name)
        upload_dir = create_upload_directory(dataset_dir)
        
        raw_data_dir = os.path.join(upload_dir, "raw_data")
        os.makedirs(raw_data_dir, exist_ok=True)
        archive_path = os.path.join(raw_data_dir, archive_file.filename)
        archive_file.save(archive_path)
        
        extracted_files, extract_error = extract_archive_file_to_upload_dir(archive_path, upload_dir, file_extension)
        if extract_error:
            return jsonify({
                "error": extract_error,
                "success_count": 0,
                "failed_count": 0,
                "extracted_files": 0,
                "upload_directory": upload_dir
            }), 400
        
        success_count = 0
        failed_files = []
        
        for file_path in extracted_files:
            file_name = os.path.basename(file_path)
            try:
                is_valid, validation_error = validate_dicom_file(file_path)
                if not is_valid:
                    failed_files.append({
                        "file": file_name,
                        "error": validation_error
                    })
                    continue
                
                orthanc_data, upload_error = upload_dicom_to_orthanc(file_path)
                if upload_error:
                    failed_files.append({
                        "file": file_name,
                        "error": upload_error
                    })
                    continue
                
                db_success, db_error = update_database_records(orthanc_data, dataset_id)
                if not db_success:
                    failed_files.append({
                        "file": file_name,
                        "error": db_error
                    })
                    continue
                
                success_count += 1
                
            except Exception as e:
                failed_files.append({
                    "file": file_name,
                    "error": str(e)
                })
        
        return jsonify({
            "message": f"Archive extraction and upload completed: {success_count} successful, {len(failed_files)} failed",
            "success": True,
            "success_count": success_count,
            "failed_count": len(failed_files),
            "failed_files": failed_files,
            "extracted_files": len(extracted_files),
            "upload_directory": upload_dir
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
            
        return jsonify({
            "error": "Failed to process archive file",
            "message": str(e),
            "success_count": 0,
            "failed_count": 0,
            "extracted_files": 0,
            "failed_files": [{"file": "archive_file", "error": str(e)}]
        }), 500