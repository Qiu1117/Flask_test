from nibabel.orientations import axcodes2ornt
from nibabel.orientations import ornt_transform
import numpy as np
import pydicom
from pydicom import dcmread
import nibabel as nib
import pathlib
from pathlib import Path
from QMR.smooth.gaussian_blur import gaussian_blur


def reorient(
    nii: nib.Nifti1Image,
    orientation="RAS",
) -> nib.Nifti1Image:
    """Reorients a nifti image to specified orientation. Orientation string or tuple
    must consist of "R" or "L", "A" or "P", and "I" or "S" in any order."""
    orig_ornt = nib.io_orientation(nii.affine)
    targ_ornt = axcodes2ornt(orientation)
    transform = ornt_transform(orig_ornt, targ_ornt)
    reoriented_nii = nii.as_reoriented(transform)
    return reoriented_nii


def loadData(path, format, reorient=True):
    if type(path) != pathlib.WindowsPath:
        path = Path(path)

    def loadDICOM(path, data_only=False):
        dcm = pydicom.dcmread(path)
        if data_only:
            slope = dcm.RescaleSlope if hasattr(dcm, "RescaleSlope") else 1
            intercept = dcm.RescaleIntercept if hasattr(dcm, "RescaleSlope") else 0
            return dcm.pixel_array * slope + intercept
        else:
            return dcm

    def loadNii(path):
        data = nib.load(path).dataobj
        if data.ndim == 3 and reorient:
            data = reorient(data)
        return data

    if format == "nifti":
        data = loadNii(path)
    elif format == "dicom":
        data = loadDICOM(path)
    elif format == "dicom_data":
        data = loadDICOM(path, data_only=True)
    else:
        raise NotImplementedError("No such model supported.")

    smoothed_data = gaussian_blur(data)
    return smoothed_data
