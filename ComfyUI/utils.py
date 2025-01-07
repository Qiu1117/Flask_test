import numpy as np
import io
from pathlib import Path
import nibabel as nib
import pydicom
from pydicom.uid import RLELossless
from pydicom import uid
from pydicom.tag import Tag
import json
from pydicom import dcmread, dataset, uid, pixel_data_handlers




def exportDICOM(dicom: pydicom.dataset.FileDataset, output_path):
    '''
        dicom must already be pydicom.dataset.FileDataset. This function should be behind update_data()
    '''
    if dicom.file_meta.TransferSyntaxUID != uid.ExplicitVRLittleEndian:
        dicom.file_meta.TransferSyntaxUID = uid.ExplicitVRLittleEndian  
        dicom.compress(RLELossless) # if not assign arr as the second parameter, it cannot compress data with compressed UID, so have to change it to explicit first

    dicom.save_as(output_path)


def export_file(source_data, source_read, file_name):
    '''
        Export 2D or 3D data to nii.gz or dcm file
        source_data: numpy array
    '''
    export_file_path = ''
    if source_data.ndim == 2 or (source_data.ndim==3 and source_data.shape[2] <= 3):
        export_file_path = file_name + '.dcm'
        exportDICOM(source_read, '../data/temp/' + export_file_path)
    elif source_data.ndim==3:
        export_file_path= file_name + '.nii.gz'
        exportNIFTI(source_read, '../data/temp/'+export_file_path)
    return export_file_path


def is_multiframe_dicom(dicom_input):
    """
    Use this function to detect if a dicom series is a siemens 4D dataset
    NOTE: Only the first slice will be checked so you can only provide an already sorted dicom directory
    (containing one series)

    :param dicom_input: directory with dicom files for 1 scan
    """
    # read dicom header
    header = dicom_input[0]

    if Tag(0x0002, 0x0002) not in header.file_meta:
        return False
    if header.file_meta[0x0002, 0x0002].value == '1.2.840.10008.5.1.4.1.1.4.1':
        return True
    return False

def is_philips(dicom_input):
    """
    Use this function to detect if a dicom series is a philips dataset

    :param dicom_input: directory with dicom files for 1 scan of a dicom_header
    """
    # read dicom header
    header = dicom_input[0]

    if 'Manufacturer' not in header or 'Modality' not in header:
        return False  # we try generic conversion in these cases

    # check if Modality is mr
    if header.Modality.upper() != 'MR':
        return False

    # check if manufacturer is Philips
    if 'PHILIPS' not in header.Manufacturer.upper():
        return False

    return True


def is_siemens(dicom_input):
    """
    Use this function to detect if a dicom series is a siemens dataset

    :param dicom_input: directory with dicom files for 1 scan
    """
    # read dicom header
    header = dicom_input[0]

    # check if manufacturer is Siemens
    if 'Manufacturer' not in header or 'Modality' not in header:
        return False  # we try generic conversion in these cases

    # check if Modality is mr
    if header.Modality.upper() != 'MR':
        return False

    if 'SIEMENS' not in header.Manufacturer.upper():
        return False

    return True

def is_image_dicom(dicom_header):
    # if not contain pixel data
    print(dicom_header.pixel_array.shape)
    if Tag(0x7FE0, 0x0010) not in dicom_header:
        return False
    else:
        return True
    

def is_valid_imaging_dicom(dicom_header):
    """
    Function will do some basic checks to see if this is a valid imaging dicom
    """
    # if it is philips and multiframe dicom then we assume it is ok
    try:
        if is_philips([dicom_header]) or is_siemens([dicom_header]):
            if is_multiframe_dicom([dicom_header]):
                return True

        if "SeriesInstanceUID" not in dicom_header:
            print("No SeriesInstanceUID")
            return False

        if "InstanceNumber" not in dicom_header:
            print("No SeriesInstanceNumber")
            return False

        if "ImageOrientationPatient" not in dicom_header or len(dicom_header.ImageOrientationPatient) < 6:
            print("Invalid ImageOrientationPatient")
            return False

        if "ImagePositionPatient" not in dicom_header or len(dicom_header.ImagePositionPatient) < 3:
            print("Invalid ImagePositionPatient")
            return False

        # for all others if there is image position patient we assume it is ok
        if Tag(0x0020, 0x0037) not in dicom_header:
            return False
        
        # if not contain pixel data
        if Tag(0x7FE0, 0x0010) not in dicom_header:
            return False
        
        return True
    except (KeyError, AttributeError):
        return False
    
def is_dicom(data, type='file'):
    '''
        Check if the file is a valid dicom file by reading the first 4 bytes of the file.
        type: 'file' or 'stream'
    '''
    if type == 'file':
        file_stream = open(data, 'rb')
    elif type == 'stream':
        file_stream = data
    file_stream.seek(128)
    header = file_stream.read(4)
    file_stream.close()
    if header == b'DICM':
        return True
    

def retrieveDICOMInstance(oid, orthanc_url):
    dicom_url = f"{orthanc_url}/instances/{oid}/file"
    response = requests.get(dicom_url)

    if response.status_code != 200:
        print("Failed to retrieve DICOM from Orthanc")
    else:
        if is_dicom(io.BytesIO(response.content), 'stream'):
            dcm = pydicom.dcmread(io.BytesIO(response.content), force=True, defer_size="1 KB")
            if is_multiframe_dicom(dcm):
                print("Multiframe DICOM Not Implemented")
            else:
                return dcm
            #else:
            #    print("No image inside the file")
        else:
            print("Not a valid DICOM file")
        
        
def update_uids(dcm, new_uids):
    '''
        Update the UIDs of the dicom file
    '''
    dcm.StudyInstanceUID = new_uids['studyuid']
    dcm.SeriesInstanceUID = new_uids['seriesuid']
    dcm.SOPInstanceUID = new_uids['instanceuid']
    return dcm


def upload_dicom(outputs, orthanc_url):
    # upload dicom to orthanc
    # output is a pydicom object, convert it to a file-like object
    results = []
    for i, output in enumerate(outputs):
        if output['type'] == 'dicom':
            file = io.BytesIO()
            pydicom.dcmwrite(file, output['data'])
            file.seek(0)
                
            upload_url = f"{orthanc_url}/instances"  # Orthanc的URL
            response = requests.post(upload_url, data=file, headers={"Content-Type": "application/dicom"})
            if (response.status_code == 200):
                results.append({'output_idx':i, 'status':'success', 'oid':response.json()['ID']})
            
        elif output['type'] == 'nifti':
            pass
    return results


def create_json(data):
    '''
        Create a json file into bytes stream
    '''
    json_data = json.dumps(data)
    file = io.BytesIO(json_data.encode())
    file.seek(0)
    return file
    

def upload_attachment(file_stream, attach_to_oid, orthanc_url, file_type='json'):
    '''
        Upload attachment to a dicom object
    '''
    upload_url = f"{orthanc_url}/instances/{attach_to_oid}/attachments/{file_type}"
    response = requests.post(upload_url, data=file_stream, headers={"Content-Type": f"application/{file_type}"})
    if (response.status_code == 200):
        return response.json()['ID']
    else:
        return None

def read_multiframe_dicom():
    pass


if __name__ == '__main__':
    orthanc_url = 'http://localhost:8042'
    oid = "4c09aa41-4af01ac9-5b744385-d1b03757-cb61f540"
    dcm = retrieveDICOMInstance(oid, orthanc_url)
    print(dcm.pixel_array.shape)
    #print(requests.get(orthanc_url+'/instances').json())