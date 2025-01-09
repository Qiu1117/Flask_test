import numpy as np
from skimage import io as skimage_io
from pathlib import Path
import nibabel as nib
import pydicom
from pydicom.uid import RLELossless
from pydicom import uid
from pydicom.tag import Tag
import json
from pydicom import dcmread, dataset, uid, pixel_data_handlers
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pydicom.sequence import Sequence
from pydicom.dataelem import DataElement
from pathlib import Path
from pydicom.uid import RLELossless, JPEG2000Lossless
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import generate_uid, UID, ImplicitVRLittleEndian
import datetime
import os

def run_file2data_converter(node, **kwargs):
    data_key = next(iter(node.inputs))  # should be only one input
    data = node.inputs[data_key].value
    
    if node.function_name == 'dicom_to_2d':
        converter_func = dicom_to_2d
        #data = node.inputs['FILE'].value
    
    elif node.function_name == 'nifti_to_3d':
        converter_func = nifti_to_3d
    
    else:
        raise ValueError("Invalid function name")
    data = converter_func(data, **kwargs)

    return data

def run_data2file_converter(node, filepath, **kwargs):
    data_key = next(iter(node.inputs))  # should be only one input
    data = node.inputs[data_key].value
    if node.function_name == '2d_to_dicom':
        converter_func = create2DFakeDICOM
        #data = node.inputs['data'].value

    elif node.function_name == '2d_to_image':
        converter_func = twoD_to_image
        #data = node.inputs['data'].value
    
    elif node.function_name == '2d_to_nifti':
        converter_func = create3DFakeNIFTI
        #data = node.inputs['data'].value
    
    elif node.function_name == '3d_to_dicom_volume':
        converter_func = createDICOMVolume
        #data = node.inputs['data'].value
    
    elif node.function_name == '3d_to_nifti':
        converter_func = create3DFakeNIFTI
        #data = node.inputs['FILE'].value
    
    else:
        raise ValueError("Invalid function name")
    filepath = converter_func(data, filepath, **kwargs)

    return filepath

def nifti_to_3d(filepath):
    '''
      obtain nifti data from path
    '''
    if type(filepath) == list:
        filepath = filepath[0]
    nifti = nib.load(filepath)
    return nifti.get_fdata()


def dicom_to_2d(filepath):
    '''
        Convert a dicom file to 2D numpy array
    '''
    if type(filepath) == list:
        filepath = filepath[0]
    ds = pydicom.dcmread(filepath)
    return ds.pixel_array


def createDICOMVolume(data, filepath):
    '''
        Create a dicom volume with 3D data
    '''
    filepath = '.'.join([filepath, 'dcm'])
    # volume = []
    # for f in Path('test').glob('*.dcm'):
    #     ds = pydicom.dcmread(f)
    #     volume.append(ds.pixel_array)
    # volume = np.array(volume)
    # Create File Meta Information

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = pydicom.uid.EnhancedCTImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    # Create a new DICOM dataset
    ds = FileDataset('', {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    # Set the necessary DICOM elements
    ds.PatientName = "Test^Patient"
    ds.PatientID = "123456"
    ds.Modality = "CT"
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    ds.SOPInstanceUID = generate_uid()
    ds.SOPClassUID = pydicom.uid.EnhancedCTImageStorage

    # Set up the necessary multi-frame functional groups
    num_frames = volume.shape[0]
    ds.NumberOfFrames = num_frames
    ds.Rows = volume.shape[1]
    ds.Columns = volume.shape[2]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1

    # Frame Increment Pointer
    ds.FrameIncrementPointer = 'PerFrameFunctionalGroupsSequence'

    # Pixel Data: Concatenate all frames
    volume = data.astype(np.uint16)
    ds.PixelData = volume.tobytes()

    # Shared Functional Groups Sequence
    ds.SharedFunctionalGroupsSequence = Sequence()
    shared_group = Dataset()
    shared_group.PixelMeasuresSequence = Sequence([Dataset()])
    shared_group.PixelMeasuresSequence[0].PixelSpacing = [1.0, 1.0]  # replace with actual pixel spacing
    shared_group.PixelMeasuresSequence[0].SliceThickness = 1.0  # replace with actual slice thickness
    ds.SharedFunctionalGroupsSequence.append(shared_group)

    # Per-frame Functional Groups Sequence
    ds.PerFrameFunctionalGroupsSequence = Sequence()

    for i in range(num_frames):
        frame_group = Dataset()
        frame_group.FrameContentSequence = Sequence([Dataset()])
        frame_group.FrameContentSequence[0].DimensionIndexValues = [i + 1]
        frame_group.PlanePositionSequence = Sequence([Dataset()])
        frame_group.PlanePositionSequence[0].ImagePositionPatient = [0, 0, i]  # replace with actual position
        ds.PerFrameFunctionalGroupsSequence.append(frame_group)

    #ds.compress(RLELossless)
    # Save the dataset to a DICOM file
    ds.save_as(filepath, write_like_original=False)
    return filepath
                                                

def twoD_to_image(data, filepath, format='png', normalize=True):
    filepath = '.'.join([filepath, format])
    if type(data) != np.ndarray:
        raise ValueError("Data must be a numpy array")
    if data.max() > 255 or data.min() < 0:
        data = (data - data.min()) / (data.max() - data.min()) * 255
    else:
        if normalize:
            data = (data - data.min()) / (data.max() - data.min()) * 255
    skimage_io.imsave(filepath, data.astype(np.uint8))
    return filepath


def create3DFakeNIFTI(data, filepath):
    '''
        Create
    '''
    filepath = '.'.join([filepath, 'dcm'])

    nifti = nib.Nifti1Image(data, np.eye(4))
    nib.save(nifti, filepath)
    return filepath


# def create2DFakeDICOM(data, filepath):
#     '''
#         Create a fake dicom file with 2D data
#     '''
#     filepath = '.'.join([filepath, 'dcm'])

#     # Populate required values for file meta information
#     file_meta = dataset.FileMetaDataset()
#     file_meta.MediaStorageSOPClassUID = uid.UID('1.2.840.10008.5.1.4.1.1.4')


#     # Create the FileDataset instance (initially no data elements, but file_meta
#     # supplied)
#     ds = dataset.FileDataset(filepath, {},
#                     file_meta=file_meta, preamble=b"\0" * 128)

#     # Write as a different transfer syntax XXX shouldn't need this but pydicom
#     # 0.9.5 bug not recognizing transfer syntax
#     ds.file_meta.TransferSyntaxUID = uid.UID('1.2.840.10008.1.2.1')

#     ds.PixelData = data.astype(np.uint16).tobytes()  #img[0,0].copy(order='C')
    
#     ds.BitsAllocated = 16
#     ds.Rows = data.shape[0]
#     ds.Columns = data.shape[1]
#     ds.SamplesPerPixel = 1
#     ds.PhotometricInterpretation = 'MONOCHROME2'
#     ds.PixelRepresentation = 1
#     ds.BitsStored = 12
#     ds.save_as(filepath, little_endian=True, implicit_vr=False)
#     return filepath


def create2DFakeDICOM(data, filepath) -> str:
    import pydicom
    import numpy as np
    import time
    import os
    
    def generate_checksum(uid):
        """生成UID校验和"""
        uid_parts = uid.split(".")
        sum_digits = [sum(int(digit) for digit in part) for part in uid_parts]
        count_digits = [len(part) if len(part) % 9 != 0 else 9 for part in uid_parts]
        checksum_digits = [
            (int(sum_digit) % count_digit)
            for sum_digit, count_digit in zip(sum_digits, count_digits)
        ]
        checksum = "".join(str(digit) for digit in checksum_digits)
        return checksum[:10] if len(checksum) > 10 else checksum

    def get_processing_type(image_type):
        """获取处理类型"""
        processing_dict = {
            "QUANT": "1",
            "MASK": "2",
            "NORMAL": "3",
            "OTHER": "4",
        }

        if len(image_type) >= 3:
            part_three = image_type[2]
            processing_type = "1" if part_three == "DEIDENT" else "0"
            processing_type += processing_dict.get(image_type[3], "")
            return processing_type
        return ""

    def generate_uid(uid, fileNum, index, image_type):
        """生成新的UID"""
        root_unique = "1.2.826.0.1.3680043.10.1338"
        uid_version = ".001"
        check_code = "." + generate_checksum(uid)
        timestamp = "." + str(int(round(time.time() * 100)))
        inputFileNum = "." + str(fileNum).zfill(2)
        index = "." + str(index).zfill(2)
        type = "." + get_processing_type(image_type)

        return (
            root_unique
            + uid_version
            + check_code
            + timestamp
            + inputFileNum
            + index
            + type
        )

    if not filepath.lower().endswith('.dcm'):
        filepath = f"{filepath}.dcm"

    reference_dicom = r"C:\Users\Qiuyi\Desktop\test.dcm"
    ds = pydicom.dcmread(reference_dicom)
    
    image_result = data.astype(np.uint16)
    ds.PixelData = image_result.tobytes()
    ds.Rows, ds.Columns = image_result.shape

    min_val = np.min(image_result)
    max_val = np.max(image_result)
    ds.WindowWidth = max_val - min_val
    ds.WindowCenter = (max_val + min_val) / 2

    ds.SamplesPerPixel = 1
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.RescaleIntercept = 0
    ds.RescaleSlope = 1

    # 更新UIDs
    for tag in [(0x08, 0x18), (0x20, 0x0E), (0x20, 0x0D)]:
        original_uid = ds[tag].value
        image_type = ds[0x08, 0x08].value
        new_uid = generate_uid(original_uid, 1, 1, image_type)
        ds[tag].value = new_uid

    # 保存文件
    ds.save_as(filepath)
    return filepath

def exportNIFTI(nifti:nib.Nifti1Image, output_path):
    '''
        nifti must already be nib.Nifti1Image. 
    '''

    nib.save(nifti, output_path)


if __name__ == '__main__':
    create3DFakeNIFTI(np.random.rand(10,10), 'test.nii.gz')