import requests
import json
import io
import pydicom
import config


def _upload_orthanc(file, filename=None):  # 保持原函数名
    upload_url = f"{config.ORTHANC_URL}/instances"
    
    is_bytesio = isinstance(file, io.BytesIO)
    
    if not hasattr(file, 'name') or not file.name:
        return {"status": "error", "message": "Empty filename"}
    
    if is_bytesio:
        stream = file
        current_position = stream.tell()
    else:
        stream = file.stream
        current_position = stream.tell()
    stream.seek(0)
    
    try:
        try:
            dicom_data = pydicom.dcmread(stream)
            
            if hasattr(dicom_data, 'SeriesDescription') and dicom_data.SeriesDescription == "DEFAULT PS SERIES" and hasattr(dicom_data, 'PixelData'):
                stream.seek(current_position)
                return {"status": "ignored", "message": "File ignored: SeriesDescription is 'DEFAULT PS SERIES'"}
            if hasattr(dicom_data, 'PixelData') is False:
                stream.seek(current_position)
                return {"status": "ignored", "message": "File ignored: PixelData is null"}
        except Exception as e:
            stream.seek(current_position)
            return {"status": "error", "message": f"Error reading DICOM data: {str(e)}"}
        
        stream.seek(0)
        headers = {"Content-Type": "application/dicom"}
        
        try:
            response = requests.post(
                upload_url, 
                data=stream,
                headers=headers,
                auth=(config.ORTHANC_USERNAME, config.ORTHANC_PASSWORD),
                timeout=60
            )
            
            stream.seek(0)
            return response
        except requests.RequestException as req_error:
            stream.seek(0)
            return {"status": "error", "message": f"Request failed: {str(req_error)}"}
        
    except Exception as e:
        stream.seek(0)
        return {"status": "error", "message": f"Upload failed: {str(e)}"}

def orthanc_request(method, endpoint, **kwargs):
    url = f"{config.ORTHANC_URL}/{endpoint.lstrip('/')}"
    auth = (config.ORTHANC_USERNAME, config.ORTHANC_PASSWORD)
    
    if 'auth' not in kwargs:
        kwargs['auth'] = auth
        
    return requests.request(method, url, **kwargs)


def get_patient_info(patient_orthanc_id):
    patient_tags_url = f"patients/{patient_orthanc_id}/shared-tags?simplify"
    response = orthanc_request("GET", patient_tags_url)
    
    if response.status_code != 200:
        print(f"Error getting patient data: {response.status_code}, {response.text}")
        return {}
    return response.json()


def get_study_info(study_orthanc_id):
    study_tags_url = f"studies/{study_orthanc_id}"
    response = orthanc_request("GET", study_tags_url)
    
    if response.status_code != 200:
        print(f"Error getting study data: {response.status_code}, {response.text}")
        return {"MainDicomTags": {}}
    return response.json()


def get_series_info(series_orthanc_id):
    series_tags_url = f"series/{series_orthanc_id}"
    response = orthanc_request("GET", series_tags_url)
    
    if response.status_code != 200:
        print(f"Error getting series data: {response.status_code}, {response.text}")
        return {"MainDicomTags": {}}
    return response.json()