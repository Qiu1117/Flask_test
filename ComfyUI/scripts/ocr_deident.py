'''
 # @ Author: Jiabo Xu
 # @ Create Time: 2023-04-23 22:05:54
 # @ Modified by: Jiabo Xu
 # @ Modified time: 2023-05-27 05:43:19
 # @ Description:
 '''


import nibabel as nib
import numpy as np
import pydicom
from paddleocr import PaddleOCR
from pydicom.uid import RLELossless
import string
from pydicom import uid
import re
from pathlib import Path
from pydicom.pixel_data_handlers.util import convert_color_space


def get_meta(data, name:str):
    '''
        For nifti data, name can be affine, header
        For dicom, name is the dicom tag name write in Capital Camel-Case
    '''
    if isinstance(data, pydicom.dataset.FileDataset):
        if hasattr(data, name):
            return getattr(data, name)
        else:
            return None
    elif isinstance(data, nib.Nifti1Image):  ## may define more detailed attr in the future, such as thickness, pixel space
        if name == 'affine':
            return data.affine
        elif name == 'header':
            return data.header
        else:
            return None
    else:
        raise NotImplementedError(type(data))
    

def exportDICOM(array_data, sources, file_name_list):
    assert len(array_data) == len(sources), "different length of the array_data and the sources"
    assert len(array_data) == len(file_name_list), "different length of the array_data and the file_name_list"

    for i in range(len(array_data)):
        ds = sources[i]
        ds.PixelData = array_data
        ds.save_as(file_name_list[i])


def exportNifti(array_data, affine, output_name):
    new_nib = nib.Nifti1Image(array_data, affine)
    nib.save(new_nib, output_name)


def get_sensitive(dcm, sensitive_list):
    info = []
    for elm in sensitive_list:
        info.append(get_meta(dcm, elm))
    return info


def get_position(four_points):
    letftop = four_points[0] 
    righttop = four_points[1] 
    rightbot = four_points[2] 
    leftbot = four_points[3] 
    return int(letftop[1]), int(letftop[0]), int(leftbot[1] - letftop[1]), int(righttop[0] - letftop[0])


def deident_ocr(dicom_obj, sensitive_list=['PatientName', 'PatientID', 'PatientBirthDate'], rectangle_roi=[{'x':0, 'y':0, 'width':0, 'height':0}], roi_only=False, use_gpu=True):    
    pi = dicom_obj.PhotometricInterpretation
    dicom_obj.PhotometricInterpretation = 'YBR_FULL'
    data = dicom_obj.pixel_array
    dicom_obj.PhotometricInterpretation = pi
    #data = convert_color_space(data, 'RGB', 'YBR_FULL')

    if not roi_only:
        ocr = PaddleOCR(use_angle_cls=True, use_gpu=use_gpu, lang='en') # need to run only once to download and load model into memory
        result = ocr.ocr(data, cls=True, det=True, rec=True)

        detection = []
        for loc, (pred, prob) in result[0]:
            detection.append({'location':loc, 'text':pred})

        tag_value_map = get_sensitive(dicom_obj, sensitive_list)
        translating = str.maketrans('', '', string.punctuation + ' ')
        for i in range(len(tag_value_map)):
            tag_value_map[i] = str(tag_value_map[i]).translate(translating)

        for term in detection:
            cleaned = term['text'].translate(translating)
            for sensit in tag_value_map:
                if re.search(sensit, cleaned):
                    y, x, h, w = get_position(term['location'])
                    data[y:y+h, x:x+w] = 1000
                    break
    if rectangle_roi:
        empty_value = (0,) * data.shape[-1] if data.ndim == 3 else 0
        for roi in rectangle_roi:
            data[roi['y']: roi['y']+roi['height'], roi['x']:roi['x']+roi['width']] = empty_value   
    
    return data


def exportDICOM(dcm, output_path, compress=False):
    #dcm.compress(RLELossless, dcm.pixel_array)
    dcm.save_as(output_path)

def exist_or_create(path):
    if not path.exists():
        path.mkdir(exist_ok=True, parents=True)


def get_test_data(test_folder, output_folder):
    output_folder = Path(output_folder)
    test_name = []
    output_path = []
    for p in Path(test_folder).rglob("*.dcm"):
        new_folder = re.sub(test_folder, output_folder, p.parent)
        print(new_folder)
        exist_or_create(new_folder)
    
    return 

if __name__ == '__main__':
    dicom_path = "G:\code\paddle_ocr\samples\T2\I160.dcm"
    us_path = "G:\\code\\paddle_ocr\\samples\\USG\\Canon\\IM-0001-0001-0001.dcm"
    us_path2 = "G:\\code\\paddle_ocr\\samples\\USG\\Philips\\IM-0001-0030-0002.dcm"
    us_path3 = "G:\\code\\paddle_ocr\\samples\\USG\\C390961A-15-2020.dcm"


    sensitive_list = ['PatientName', 'PatientID', 'PatientBirthDate']
    dcm = pydicom.dcmread(us_path)
    deidented_data = deident_ocr(dcm, sensitive_list, [{'x': 10, 'y':10, 'width':450, 'height': 450}])

    ## export
    if dcm.BitsAllocated == 16:
        dcm.PixelData = deidented_data.astype(np.int16).tobytes()
    elif dcm.BitsAllocated == 8:
        dcm.PixelData = deidented_data.astype(np.int8).tobytes()

    if dcm.file_meta.TransferSyntaxUID != uid.ExplicitVRLittleEndian:
        dcm.file_meta.TransferSyntaxUID = uid.ExplicitVRLittleEndian
        dcm.compress(RLELossless)

    dcm.save_as('de_output_1.dcm')

    #get_test_data("samples", '')