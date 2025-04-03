# %% base import
import numpy as np
from QMR.smooth.gaussian_blur import gaussian_blur
import pydicom
import io
import time
import json
import requests
import uuid
from flask import request, Blueprint, send_file, jsonify, make_response, abort
import os
from middleware import token_required
from datetime import datetime
from CRUD import _upload_orthanc, _new_study_pair, _new_series_pair, _new_instance_pair
from db_models import (
    db,
    Account,
    Group,
    Acc_Group,
    Dataset_Group,
    Dataset,
    Patient,
    Dataset_Patients,
    Dataset_Studies,
    Dataset_Series,
    Dataset_Instances,
)
from sqlalchemy import update, text, func, and_, or_
from QMR.MPFSL import MPFSL


mpf = Blueprint("mpf", __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
MPFUPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "mpf")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MPFUPLOAD_FOLDER, exist_ok=True)

orthanc_url = "http://127.0.0.1:8042"
orthanc_username = "orthanc"
orthanc_password = "orthanc"


def orthanc_request(method, endpoint, **kwargs):
    url = f"{orthanc_url}/{endpoint.lstrip('/')}"
    auth = (orthanc_username, orthanc_password)
    
    # 如果没有指定auth参数，添加默认认证
    if 'auth' not in kwargs:
        kwargs['auth'] = auth
        
    return requests.request(method, url, **kwargs)


def QMR_Cal(realctr, ictr, tsl, B1_path, dict_path):

    dyn_real1 = realctr[0]
    dyn_real2 = realctr[2]
    dyn_real3 = realctr[1]
    dyn_real4 = realctr[3]

    dyn_img1 = ictr[0]
    dyn_img2 = ictr[2]
    dyn_img3 = ictr[1]
    dyn_img4 = ictr[3]

    mpfsl = MPFSL(
        dyn_real1,
        dyn_img1,
        dyn_real2,
        dyn_img2,
        dyn_real3,
        dyn_img3,
        dyn_real4,
        dyn_img4,
        dict_path,
        B1_path,
        tsl,
    )

    mpf = mpfsl.cal_mpf()
    mpf_result = (mpf * 1000).astype(np.uint16)

    rmpf = mpfsl.rmpfsl
    rmpf = np.clip(rmpf, np.min(rmpf), 4, out=None)
    rmpf_result = (rmpf * 100).astype(np.uint16)

    return rmpf_result, mpf_result


def save2dcm(template_dcm, pixel_data,file_prefix, formatted_date, new_study_uid):
    ds = pydicom.dcmread(template_dcm)
    ds.PixelData = pixel_data.tobytes()
    rows, columns = pixel_data.shape
    ds.Rows = rows
    ds.Columns = columns

    min_val = np.min(pixel_data)
    max_val = np.max(pixel_data)
    window_width = max_val - min_val
    window_level = (max_val + min_val) / 2

    original_study_description = ds.StudyDescription
    ds.StudyDescription = f"{original_study_description}_Processed_{formatted_date}"

    original_series_description = (
        ds[0x0008, 0x103E].value if (0x0008, 0x103E) in ds else "Unknown Series"
    )
    ds[0x0008, 0x103E].value = f"{original_series_description}_{file_prefix}_{formatted_date}"

    ds[0x0018, 0x1030].value = (
        f"{file_prefix}_Result_{formatted_date}"
    )

    ds.WindowWidth = window_width
    ds.WindowCenter = window_level
    # imagetype
    ds.SamplesPerPixel = 1  # 对于灰度图像，每个像素只包含一个样本
    ds.BitsAllocated = 16  # 每个样本使用16位进行编码
    ds.BitsStored = 16  # 每个样本使用16位进行存储
    ds.HighBit = 15  # 最高有效位为第15位
    ds.RescaleIntercept = 0
    ds.RescaleSlope = 1

    instance_uid = ds[0x08, 0x18].value
    series_uid = ds[0x20, 0x0E].value
    study_uid = ds[0x20, 0x0D].value
    imageType = ds[0x08, 0x08].value

    fileNum = 1
    index = 1
    new_uid = generate_uid(instance_uid, fileNum, index, imageType)
    ds[0x08, 0x18].value = new_uid

    new_uid = generate_uid(series_uid, fileNum, index, imageType)
    ds[0x20, 0x0E].value = new_uid

    # new_uid = generate_uid(study_uid, fileNum, index, imageType)
    ds[0x20, 0x0D].value = new_study_uid

    return ds


def generate_checksum(uid):
    uid_parts = uid.split(".")

    sum_digits = [sum(int(digit) for digit in part) for part in uid_parts]

    count_digits = [len(part) if len(part) % 9 != 0 else 9 for part in uid_parts]

    checksum_digits = [
        (int(sum_digit) % count_digit)
        for sum_digit, count_digit in zip(sum_digits, count_digits)
    ]

    checksum = "".join(str(digit) for digit in checksum_digits)

    if len(checksum) > 10:
        checksum = checksum[:10]

    return checksum


def get_processing_type(image_type):
    processing_dict = {
        "QUANT": "1",
        "MASK": "2",
        "NORMAL": "3",
        "OTHER": "4",
    }

    processing_type = ""

    if len(image_type) >= 3:
        part_three = image_type[2]

        if part_three == "DEIDENT":
            processing_type += "1"
        else:
            processing_type += "0"
        processing_type += processing_dict.get(image_type[3], "")
        return processing_type

    return ""


def generate_uid(uid, fileNum, index, image_type):
    root_unique = "1.2.826.0.1.3680043.10.1338"
    uid_version = ".001"

    check_code = "." + generate_checksum(uid)

    timestamp = "." + str(int(round(time.time() * 100)))

    inputFileNum = "." + str(fileNum).zfill(2)

    index = "." + str(index).zfill(2)

    type = "." + get_processing_type(image_type)

    new_uid = (
        root_unique + uid_version + check_code + timestamp + inputFileNum + index + type
    )

    return new_uid


def process_and_upload_file(
    realctr, data, file_prefix, UPLOAD_FOLDER, orthanc_url, Dataset_ID, new_study_uid
):
    current_date = datetime.now()
    formatted_date = current_date.strftime("%Y%m%d%H%M")

    result = save2dcm(realctr[0], data, file_prefix, formatted_date, new_study_uid)
    new_uuid = str(uuid.uuid4())
    filename = f"{file_prefix}_{new_uuid}.dcm"
    output_dicom_path = os.path.join(UPLOAD_FOLDER, filename)
    result.save_as(output_dicom_path)

    with open(output_dicom_path, "rb") as f:
        file = f.read()
    upload_url = f"{orthanc_url}/instances"
    response = requests.post(
        upload_url, 
        data=file, 
        headers={"Content-Type": "application/dicom"},
        auth=(orthanc_username, orthanc_password)  # 添加认证
    )
    orthanc_data = json.loads(response.content)

    study_pair = Dataset_Studies.query.filter(
        and_(
            Dataset_Studies.patient_orthanc_id == orthanc_data["ParentPatient"],
            Dataset_Studies.study_orthanc_id == orthanc_data["ParentStudy"],
            Dataset_Studies.dataset_id == Dataset_ID,
        )
    ).first()
    if study_pair is None:
        _new_study_pair(orthanc_data, Dataset_ID)

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

    instance_pair = Dataset_Instances.query.filter(
        and_(
            Dataset_Instances.series_orthanc_id == orthanc_data["ParentSeries"],
            Dataset_Instances.instance_orthanc_id == orthanc_data["ID"],
        )
    ).first()
    if instance_pair is None:
        _new_instance_pair(orthanc_data)

    return output_dicom_path, orthanc_data["ID"]


@mpf.route("/mpf", methods=["POST"])
@token_required()
def MPF_cal():

    realctr = []
    ictr = []
    tsl = float(request.form.get("Tsl"))
    Dataset_ID = request.form.get("Dataset_ID")

    b1_map_file = request.files.get('B1_map')
    b1_path = os.path.join(UPLOAD_FOLDER, b1_map_file.filename)
    b1_map_file.save(b1_path)

    dictionary_file = request.files.get('Dictionary')
    dic_path = os.path.join(UPLOAD_FOLDER, dictionary_file.filename)
    dictionary_file.save(dic_path)

    file_list = request.form.get("Fileid_List").split(",")
    if len(file_list) == 0:
        return "No files uploaded."

    for i in range(0, len(file_list), 2):
        item1 = file_list[i]
        item2 = file_list[i + 1] if i + 1 < len(file_list) else None

        if item1:
            Instance_url1 = f"{orthanc_url}/instances/{item1}/file"
            response1 = requests.get(Instance_url1, auth=(orthanc_username, orthanc_password))
            file_path1 = os.path.join(UPLOAD_FOLDER, f"instance_{item1}.dcm")
            with open(file_path1, "wb") as file1:
                file1.write(response1.content)
            ds1 = pydicom.dcmread(file_path1)
            if ds1.ImageType[3].upper() == "R":
                realctr.append(file_path1)
            elif ds1.ImageType[3].upper() == "I":
                ictr.append(file_path1)

        if item2:
            Instance_url2 = f"{orthanc_url}/instances/{item2}/file"
            response2 = requests.get(Instance_url2, auth=(orthanc_username, orthanc_password))
            file_path2 = os.path.join(UPLOAD_FOLDER, f"instance_{item2}.dcm")
            with open(file_path2, "wb") as file2:
                file2.write(response2.content)
            ds2 = pydicom.dcmread(file_path2)
            if ds2.ImageType[3].upper() == "R":
                realctr.append(file_path2)
            elif ds2.ImageType[3].upper() == "I":
                ictr.append(file_path2)

        if len(realctr) != len(ictr):
            return jsonify({"message": "Real and imaginary data do not match"}), 500

    rmpf, mpf = QMR_Cal(realctr, ictr, tsl, b1_path, dic_path)

    original_ds = pydicom.dcmread(realctr[0])
    original_study_uid = original_ds.StudyInstanceUID
    imageType = original_ds[0x08, 0x08].value

    new_study_uid = generate_uid(original_study_uid, 1, 1, imageType)

    rmpf_dicom_path, rmpf_orthanc_id = process_and_upload_file(
        realctr, rmpf, "Rmpfsl", UPLOAD_FOLDER, orthanc_url, Dataset_ID, new_study_uid
    )

    mpf_dicom_path, mpf_orthanc_id = process_and_upload_file(
        realctr, mpf, "MPF", UPLOAD_FOLDER, orthanc_url, Dataset_ID, new_study_uid
    )

    response = make_response(send_file(mpf_dicom_path, mimetype="application/dicom"))
    response.headers["X-RMPF-Orthanc-ID"] = rmpf_orthanc_id
    response.headers["X-MPF-Orthanc-ID"] = mpf_orthanc_id
    response.headers["Access-Control-Expose-Headers"] = "*"

    return response


@mpf.route("/get_QMR_file", methods=["GET"])
@token_required()
def retrieve_QMR_file():
    Orthanc_Id = request.args.get("Orthanc_Id")

    if (Orthanc_Id):
        dicom_url = f"{orthanc_url}/instances/{Orthanc_Id}/file"
        response = requests.get(dicom_url, auth=(orthanc_username, orthanc_password))

        if response.status_code != 200:
            abort(response.status_code, description="Failed to retrieve DICOM from Orthanc")
        file_name = f"{Orthanc_Id}.dcm"
        file_path = os.path.join(UPLOAD_FOLDER, file_name)

        with open(file_path, "wb") as file:
            file.write(response.content)
        response = make_response(send_file(file_path, mimetype="application/dicom"))

        return send_file(file_path, mimetype="application/dicom")

    else:
        return (
            jsonify({"status": "error", "message": "The file was not found!"}),
            500,
        )
