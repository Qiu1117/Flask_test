# %% base import
import numpy as np
from QMR.smooth.gaussian_blur import gaussian_blur
import pydicom
import time
import datetime
import json
import requests
from flask import request, Blueprint, send_file, jsonify
import os
from middleware import token_required
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


# %% MPFSL
from QMR.MPFSL import MPFSL

colorbar = None
mpf = Blueprint("mpf", __name__)

UPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads"
MPFUPLOAD_FOLDER = r"C:\Users\Qiuyi\Desktop\uploads\mpf"
orthanc_url = "http://127.0.0.1:8042"


def QMR_main(realctr, ictr, tsl):
    global colorbar
    dict_path = "QMR/MPFSL/proc_dict4MPF_liver.mat"
    B1_path = "samples/0005_B1 map/I0110.dcm"

    # dyn_real1 = "samples/0005_dyn_dicom/I0050.dcm"
    # dyn_real2 = "samples/0005_dyn_dicom/I0060.dcm"
    # dyn_real3 = "samples/0005_dyn_dicom/I0070.dcm"
    # dyn_real4 = "samples/0005_dyn_dicom/I0080.dcm"

    # dyn_img1 = "samples/0005_dyn_dicom/I0090.dcm"
    # dyn_img2 = "samples/0005_dyn_dicom/I0100.dcm"
    # dyn_img3 = "samples/0005_dyn_dicom/I0110.dcm"
    # dyn_img4 = "samples/0005_dyn_dicom/I0120.dcm"
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
    mpf_result = (mpf * 100).astype(np.uint16)

    # image_path = r"C:\Users\Qiuyi\Desktop\uploads\mpf\Mpf_output.jpg"
    # plt.imshow(mpf, cmap="jet")
    # if colorbar is None:
    #     colorbar = plt.colorbar()
    # else:
    #     plt.colorbar(cax=colorbar.ax)
    # plt.savefig(image_path, format="jpeg", dpi=300, bbox_inches="tight")

    ds = pydicom.dcmread(dyn_real1)
    ds.PixelData = mpf_result.tobytes()
    rows, columns = mpf_result.shape
    ds.Rows = rows
    ds.Columns = columns

    min_val = np.min(mpf_result)
    max_val = np.max(mpf_result)
    window_width = max_val - min_val
    window_level = (max_val + min_val) / 2

    now = datetime.datetime.now()
    formatted_time = now.strftime("%Y%m%d%H%M")
    ds.ProtocolName = "MPF" + formatted_time

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

    # test_uid = "1.2.826.0.1.3680043.10.1338"
    fileNum = 1
    index = 1
    new_uid = generate_uid(instance_uid, fileNum, index, imageType)
    ds[0x08, 0x18].value = new_uid

    new_uid = generate_uid(series_uid, fileNum, index, imageType)
    ds[0x20, 0x0E].value = new_uid

    new_uid = generate_uid(study_uid, fileNum, index, imageType)
    ds[0x20, 0x0D].value = new_uid

    # output_dicom_path = r"C:\Users\Qiuyi\Desktop\uploads\mpf\Mpf_output.dcm"
    # ds.save_as(output_dicom_path)

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


@mpf.route("/mpf", methods=["POST"])
@token_required()

def rmpfsl_cal():
    realctr = []
    ictr = []
    tsl = float(request.args.get("tsl"))
    Dataset_ID = request.args.get("dataset_id")

    if len(request.json["files"]) == 0:
        return "No files uploaded."

    file_list = request.json["files"]
    for i in range(0, len(file_list), 2):
        item1 = file_list[i]
        item2 = file_list[i + 1] if i + 1 < len(file_list) else None

        instance_name1, instance_id1 = next(iter(item1.items()))
        Instance_url1 = f"{orthanc_url}/instances/{instance_id1['id']}/file"
        response1 = requests.get(Instance_url1)
        file_path1 = os.path.join(UPLOAD_FOLDER, instance_name1)
        with open(file_path1, "wb") as file1:
            file1.write(response1.content)
        ds1 = pydicom.dcmread(file_path1)
        if ds1.ImageType[3] in ["R", "r"]:
            realctr.append(file_path1)
        elif ds1.ImageType[3] in ["I", "i"]:
            ictr.append(file_path1)

        instance_name2, instance_id2 = next(iter(item2.items()))
        Instance_url2 = f"{orthanc_url}/instances/{instance_id2['id']}/file"
        response2 = requests.get(Instance_url2)
        file_path2 = os.path.join(UPLOAD_FOLDER, instance_name2)
        with open(file_path2, "wb") as file2:
            file2.write(response2.content)
        ds2 = pydicom.dcmread(file_path2)
        if ds2.ImageType[3] in ["R", "r"]:
            realctr.append(file_path2)
        elif ds2.ImageType[3] in ["I", "i"]:
            ictr.append(file_path2)

        if len(realctr) != len(ictr):
            return jsonify({"message": "Real and imaginary data do not match"}), 500

    result = QMR_main(realctr, ictr, tsl)
    SOPInstanceUID = result.SOPInstanceUID
    output_dicom_path = os.path.join(UPLOAD_FOLDER, SOPInstanceUID)
    result.save_as(output_dicom_path)


    with open(output_dicom_path, "rb") as f:
        file = f.read()
    upload_url = f"{orthanc_url}/instances"
    response = requests.post(
        upload_url, data=file, headers={"Content-Type": "application/dicom"}
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
            Dataset_Instances.instance_orthanc_id == orthanc_data["ID"]
        )
    ).first()
    if instance_pair is None:
        _new_instance_pair(orthanc_data)

    return send_file(output_dicom_path, mimetype="application/dicom")


# %% T1rho
# from QMR.t1rho import ab_fitting

# image_list = [
#     "samples/t1rho_test/dicom/I0010.dcm",
#     "samples/t1rho_test/dicom/I0020.dcm",
#     "samples/t1rho_test/dicom/I0030.dcm",
#     "samples/t1rho_test/dicom/I0040.dcm",
# ]
# tsl = [0, 0.01, 0.03, 0.05]


# t1rho = ab_fitting(tsl, image_list)
# res = t1rho.fit()

# plt.figure(1)
# plt.imshow(res, vmin=0.02, vmax=0.06, cmap="jet")
# plt.colorbar()
# plt.title("T1rho(ab_fitting)")
# plt.show()
# # %%
