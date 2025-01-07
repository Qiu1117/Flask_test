import sys
sys.path.append('..')

from dicom2nifti import dicom_array_to_nifti
from dicom2nifti import common
import pydicom
from pathlib import Path
import nibabel as nib
import numpy as np

def get_nifti(data):
    return data