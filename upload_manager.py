import os
import json
import base64
import io
import zipfile
import tarfile
import rarfile
import py7zr
from datetime import datetime
from flask import request, jsonify, g
import pydicom
import requests
import config
from Encryption import decrypt_file, decrypt_form_data, load_private_key
from db_models import Dataset


def create_dataset_directory(dataset_id, dataset_name=None):
    """Create directory structure for dataset storage"""
    base_dir = "datasets"
    os.makedirs(base_dir, exist_ok=True)
    
    if dataset_name:
        dataset_dir = os.path.join(base_dir, f"{dataset_name}_{dataset_id}")
    else:
        dataset_dir = os.path.join(base_dir, f"dataset_{dataset_id}")
    
    os.makedirs(dataset_dir, exist_ok=True)
    return dataset_dir


def create_upload_directory(dataset_dir):
    """Create timestamped upload directory"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_dir = os.path.join(dataset_dir, f"upload_{timestamp}")
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def save_uploaded_files(files, upload_dir, is_encrypted=False, aes_key=None, form_data=None):
    """Save uploaded files to local directory"""
    saved_files = []
    raw_data_dir = os.path.join(upload_dir, "raw_data")
    os.makedirs(raw_data_dir, exist_ok=True)
    
    for i, file in enumerate(files):
        try:
            file_content = file.read()
            
            if is_encrypted:
                file_index = i
                iv_key = f"iv_{file_index}"
                if iv_key in form_data:
                    iv = base64.b64decode(form_data.get(iv_key))
                    decrypted_content = decrypt_file(file_content, iv, aes_key)
                    file_content = decrypted_content
            
            file_path = os.path.join(raw_data_dir, file.filename)
            counter = 1
            base_name, ext = os.path.splitext(file.filename)
            while os.path.exists(file_path):
                new_filename = f"{base_name}_{counter}{ext}"
                file_path = os.path.join(raw_data_dir, new_filename)
                counter += 1
            
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            saved_files.append(file_path)
            file.seek(0)
            
        except Exception as e:
            print(f"Error saving file {file.filename}: {str(e)}")
            
    return saved_files


def extract_archive_file_to_upload_dir(archive_path, upload_dir, file_extension=None):
    """Extract archive file to upload directory"""
    extracted_files = []
    tmp_dir = os.path.join(upload_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        if file_extension == '.zip':
            return _extract_zip(archive_path, tmp_dir)
        elif file_extension == '.rar':
            return _extract_rar(archive_path, tmp_dir)
        elif file_extension == '.7z':
            return _extract_7z(archive_path, tmp_dir)
        elif file_extension in ['.tar', '.gz', '.bz2', '.xz']:
            return _extract_tar(archive_path, tmp_dir)
        else:
            # Fallback to zip for backward compatibility
            return _extract_zip(archive_path, tmp_dir)
            
    except Exception as e:
        return None, f"Error extracting archive: {str(e)}"


def _extract_zip(archive_path, tmp_dir):
    """Extract ZIP file"""
    extracted_files = []
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            for entry in zip_ref.infolist():
                if not entry.is_dir():
                    file_name = os.path.basename(entry.filename)
                    zip_ref.extract(entry, tmp_dir)
                    
                    extracted_file_path = os.path.join(tmp_dir, entry.filename)
                    new_file_path = os.path.join(tmp_dir, file_name)

                    if extracted_file_path != new_file_path:
                        counter = 1
                        base_name, ext = os.path.splitext(file_name)
                        while os.path.exists(new_file_path):
                            new_file_name = f"{base_name}_{counter}{ext}"
                            new_file_path = os.path.join(tmp_dir, new_file_name)
                            counter += 1

                        os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
                        os.rename(extracted_file_path, new_file_path)

                    extracted_files.append(new_file_path)
        return extracted_files, None
    except zipfile.BadZipFile as e:
        return None, f"Invalid ZIP file: {str(e)}"


def _extract_rar(archive_path, tmp_dir):
    """Extract RAR file"""
    extracted_files = []
    try:
        with rarfile.RarFile(archive_path, 'r') as rar_ref:
            for entry in rar_ref.infolist():
                if not entry.is_dir():
                    file_name = os.path.basename(entry.filename)
                    rar_ref.extract(entry, tmp_dir)
                    
                    extracted_file_path = os.path.join(tmp_dir, entry.filename)
                    new_file_path = os.path.join(tmp_dir, file_name)

                    if extracted_file_path != new_file_path:
                        counter = 1
                        base_name, ext = os.path.splitext(file_name)
                        while os.path.exists(new_file_path):
                            new_file_name = f"{base_name}_{counter}{ext}"
                            new_file_path = os.path.join(tmp_dir, new_file_name)
                            counter += 1

                        os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
                        os.rename(extracted_file_path, new_file_path)

                    extracted_files.append(new_file_path)
        return extracted_files, None
    except Exception as e:
        return None, f"Invalid RAR file: {str(e)}"


def _extract_7z(archive_path, tmp_dir):
    """Extract 7Z file"""
    extracted_files = []
    try:
        with py7zr.SevenZipFile(archive_path, 'r') as sz_ref:
            sz_ref.extractall(tmp_dir)
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    extracted_files.append(file_path)
        return extracted_files, None
    except Exception as e:
        return None, f"Invalid 7Z file: {str(e)}"


def _extract_tar(archive_path, tmp_dir):
    """Extract TAR file (including .tar.gz, .tar.bz2, .tar.xz)"""
    extracted_files = []
    try:
        with tarfile.open(archive_path, 'r:*') as tar_ref:
            for entry in tar_ref:
                if entry.isfile():
                    file_name = os.path.basename(entry.name)
                    tar_ref.extract(entry, tmp_dir)
                    
                    extracted_file_path = os.path.join(tmp_dir, entry.name)
                    new_file_path = os.path.join(tmp_dir, file_name)

                    if extracted_file_path != new_file_path:
                        counter = 1
                        base_name, ext = os.path.splitext(file_name)
                        while os.path.exists(new_file_path):
                            new_file_name = f"{base_name}_{counter}{ext}"
                            new_file_path = os.path.join(tmp_dir, new_file_name)
                            counter += 1

                        os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
                        os.rename(extracted_file_path, new_file_path)

                    extracted_files.append(new_file_path)
        return extracted_files, None
    except Exception as e:
        return None, f"Invalid TAR file: {str(e)}"


def validate_dicom_file(file_path):
    """Validate DICOM file requirements"""
    try:
        with open(file_path, 'rb') as file:
            dicom_data = pydicom.dcmread(file)
            
            if hasattr(dicom_data, 'SeriesDescription') and dicom_data.SeriesDescription == "DEFAULT PS SERIES" and hasattr(dicom_data, 'PixelData'):
                return False, "File ignored: SeriesDescription is 'DEFAULT PS SERIES'"
                
            if hasattr(dicom_data, 'PixelData') is False:
                return False, "File ignored: PixelData is null"
            
            return True, None
    except Exception as e:
        return False, f"Error reading DICOM data: {str(e)}"


def upload_dicom_to_orthanc(file_path):
    """Upload DICOM file to Orthanc server"""
    try:
        upload_url = f"{config.ORTHANC_URL}/instances"
        headers = {"Content-Type": "application/dicom"}
        
        with open(file_path, 'rb') as file:
            response = requests.post(
                upload_url,
                data=file,
                headers=headers,
                auth=(config.ORTHANC_USERNAME, config.ORTHANC_PASSWORD),
                timeout=60
            )
        
        if response.status_code != 200:
            error_message = response.content.decode('utf-8') if hasattr(response, 'content') else "Unknown error"
            return None, f"HTTP {response.status_code}: {error_message}"
        
        try:
            orthanc_data = json.loads(response.content)
            return orthanc_data, None
        except json.JSONDecodeError:
            return None, "Invalid JSON response from server"
    except Exception as e:
        return None, f"Upload error: {str(e)}"


def process_upload_request():
    """Process upload request and return parsed data"""
    form_data = request.form
    is_encrypted = form_data.get("is_encrypted", "false").lower() == "true"
    
    if is_encrypted:
        private_key = load_private_key()
        decrypted_data = decrypt_form_data(form_data, private_key)
        aes_key = decrypted_data["aes_key"]
        dataset_data = decrypted_data.get("dataset_data", {})
    else:
        aes_key = None
        dataset_data = json.loads(form_data.get("dataset_data", "{}"))
    
    dataset_id = dataset_data.get("dataset_id")
    if not dataset_id:
        return None, None, None, None, "Missing dataset ID"
    
    dataset = Dataset.query.filter_by(id=dataset_id).first()
    if dataset is None:
        return None, None, None, None, "Dataset not found"
    
    files = []
    for key in request.files.keys():
        if key.startswith("file"):
            files.extend(request.files.getlist(key))
    
    if len(files) == 0:
        return None, None, None, None, "No files uploaded"
    
    return dataset_id, dataset, files, (is_encrypted, aes_key, form_data), None