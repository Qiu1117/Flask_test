from ComfyUI.dicom2nifti import dicom_series_to_nifti, dicom_array_to_nifti
import ComfyUI.dicom2nifti
import ComfyUI.dicom2nifti.common as common
import pydicom
from pathlib import Path
import nibabel as nib
import numpy as np
from ComfyUI.utils import is_image_dicom


def fileList2nifti(folder_path, resample=True, reorient_nifti=True, output_dicom_list=False, output_path=None):
    '''
        input
            list<str> file_list: list of dicom file, must be a complete series
            boolean resample: if resample
            boolean reorient_nifti: if reorient
            output_dicom_list: if True also output the dicom object list as the second output. Only work when there is more than one dicom. 
            string output_path: use this parameter to directly output nifti or dicom file. 

        return 
            if single file, return pydicom.dataset.FileDataset 
            if multiple files, return nibabel.Nifti1Image 
            Plugins should follow the standard of these third-party library

    '''
    ComfyUI.dicom2nifti.settings.resample = resample
    ComfyUI.dicom2nifti.settings.pydicom_read_force = True
    file_list = []
    for i in Path(folder_path).glob('*.dcm'):
        file_list.append(str(i))

    dicom_input = []
    if len(file_list) != 0:
        if len(file_list) == 1:
            dicom = pydicom.read_file(file_list[0])
            return dicom
        else:
            for file_path in file_list:
                if common.is_dicom_file(file_path):
                    dicom_headers = pydicom.read_file(file_path,
                                                        defer_size="1 KB",
                                                        stop_before_pixels=False,
                                                        force=ComfyUI.dicom2nifti.settings.pydicom_read_force)
                    if common.is_valid_imaging_dicom(dicom_headers):
                        dicom_input.append(dicom_headers)

            if len(dicom_input) == 1:
                if output_path:
                    dicom_input[0].save_as(output_path)
                else:
                    return dicom_input[0]
            elif len(dicom_input) == 0:
                raise RuntimeError("No valid dicom")
            else:
                nifti = dicom_array_to_nifti(dicom_input, None, reorient_nifti)['NII']
                if output_path:
                    nib.save(nifti, output_path)
                else:
                    if output_dicom_list:
                        return nifti, dicom_input
                    else:
                        return nifti
    else:
        raise RuntimeError("No File Input")
    

def dicomList2nifti(dicom_list, resample=True, reorient_nifti=True, output_dicom_list=False, output_path=None):
    '''
        input
            list<str> file_list: list of dicom file, must be a complete series
            boolean resample: if resample
            boolean reorient_nifti: if reorient
            output_dicom_list: if True also output the dicom object list as the second output. Only work when there is more than one dicom. 
            string output_path: use this parameter to directly output nifti or dicom file. 

        return 
            if single file, return pydicom.dataset.FileDataset 
            if multiple files, return nibabel.Nifti1Image 
            Plugins should follow the standard of these third-party library

    '''
    ComfyUI.dicom2nifti.settings.resample = resample
    ComfyUI.dicom2nifti.settings.pydicom_read_force = True

    dicom_input = []
    if len(dicom_list) != 0:
        if len(dicom_list) == 1:
            return dicom_list[0]
        else:
            for i, dcm in enumerate(dicom_list):
                if is_image_dicom(dcm):
                    dicom_input.append(dcm)
                else:
                    print(f"Skip #{i} DICOM due to no image data")
            if len(dicom_input) == 1:
                if output_path:
                    dicom_input[0].save_as(output_path)
                else:
                    return dicom_input[0]
            elif len(dicom_input) == 0:
                raise RuntimeError("No valid dicom")
            else:
                nifti = dicom_array_to_nifti(dicom_input, None, reorient_nifti)['NII']
                if output_path:
                    nib.save(nifti, output_path)
                else:
                    if output_dicom_list:
                        return nifti, dicom_input
                    else:
                        return nifti
    else:
        raise RuntimeError("No File Input")

def get_data(data):
    if isinstance(data, pydicom.dataset.FileDataset):
        return data.pixel_array
    elif isinstance(data, nib.Nifti1Image):
        return data.dataobj
    else:
        raise NotImplementedError(type(data))


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
    

def update_dicom(ori_data, new_data, meta:dict=None):
    '''
        if meta not None, it must be a dictionary whose key is valid to dicom or if its nifti, meta must be {'affine': xxx}
    '''
    if isinstance(ori_data, pydicom.dataset.FileDataset):
        print(ori_data.BitsAllocated)
        if ori_data.BitsAllocated == 16:
            ori_data.PixelData = new_data.astype(np.int16).tobytes()
        elif ori_data.BitsAllocated == 8:
            ori_data.PixelData = new_data.astype(np.int8).tobytes()
        else:
            raise NotImplementedError(f"BitsAllocated is {ori_data.BitsAllocated}, which is unhandled")
        if meta:
            for k, v in meta.items():
                if hasattr(ori_data, k):
                    setattr(ori_data, k, v) 
                else:
                    raise KeyError(f"no such tag for this DICOM or wrong name for key {k}")
        return ori_data
    elif isinstance(ori_data, nib.Nifti1Image):  ## may define more detailed attr in the future, such as thickness, pixel space
        new_data_32 = new_data.astype(np.int32)  # force the format to be int32
        
        if meta and 'affine' in meta.keys():
            new = nib.Nifti1Image(new_data_32, affine=meta['affine'])
            del ori_data  # volume data is very memory-consuming
            return new
        else:
            new = nib.Nifti1Image(new_data_32, affine=ori_data.affine)
            del ori_data
            return new
    else:
        raise NotImplementedError("ori_data should either dicom or nifti object")
        


if __name__ == '__main__':
    ###### test code
    path = Path("D:\Liver Fibrosis\Better\Liver2021\Liver2021_anonymous\data\patient0000\MR_T2WFS 4MM_FB")
    file_list = []
    for f in path.glob('*'):
        file_list.append(str(f))


    ### single dicom file
    nifti = fileList2nifti([file_list[0]])

    ### multi dicom file
    # nifti = fileList2nifti(file_list)
    a = get_data(nifti)
    a = a + 1000
    print(a.shape)
    # b = get_meta(nifti, 'affine')

    #print(nifti.header)
    b = update_data(nifti, a, {'SliceThickness': 40})

    #b.save_as('asd.dcm')

    print(b.SliceThickness)
