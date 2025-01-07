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


def create2DFakeDICOM(data, filepath):
    '''
        Create a fake dicom file with 2D data
    '''
    filepath = '.'.join([filepath, 'dcm'])

    # Populate required values for file meta information
    file_meta = dataset.FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = uid.UID('1.2.840.10008.5.1.4.1.1.4')


    # Create the FileDataset instance (initially no data elements, but file_meta
    # supplied)
    ds = dataset.FileDataset(filepath, {},
                    file_meta=file_meta, preamble=b"\0" * 128)

    # Write as a different transfer syntax XXX shouldn't need this but pydicom
    # 0.9.5 bug not recognizing transfer syntax
    ds.file_meta.TransferSyntaxUID = uid.UID('1.2.840.10008.1.2.1')

    ds.PixelData = data.astype(np.uint16).tobytes()  #img[0,0].copy(order='C')
    
    ds.BitsAllocated = 16
    ds.Rows = data.shape[0]
    ds.Columns = data.shape[1]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.PixelRepresentation = 1
    ds.BitsStored = 12
    ds.save_as(filepath, little_endian=True, implicit_vr=False)
    return filepath


def exportNIFTI(nifti:nib.Nifti1Image, output_path):
    '''
        nifti must already be nib.Nifti1Image. 
    '''

    nib.save(nifti, output_path)


if __name__ == '__main__':
    create3DFakeNIFTI(np.random.rand(10,10), 'test.nii.gz')