# File: cal_rmpfsl.py
# Project: buildDICOM_dataset
# Created Date: Th May 2022
# Author: Jiabo Xu
# --------------------------------------------------------------------------
# Last Modified: Thu Jun 02 2022
# Modified By: Jiabo Xu
# Version = 1.0
# Copyright (c) 2022 CUHK


"""
DESCRIPTION: 

CHANGES: 

"""
import numpy as np
from scipy import io
import pathlib
from pathlib import Path
import matplotlib.pyplot as plt
from skimage import transform
import numpy as np
from pydicom import dcmread


from QMR.utils import reorient, loadData


class MPFSL:
    def __init__(
        self,
        dyn_real1,
        dyn_img1,
        dyn_real2,
        dyn_img2,
        dyn_real3,
        dyn_img3,
        dyn_real4,
        dyn_img4,
        dic,
        B1_map,
        tsl,
    ):
        self.dyn_cpx1 = self.to_complex(dyn_real1, dyn_img1)
        self.dyn_cpx2 = self.to_complex(dyn_real2, dyn_img2)
        self.dyn_cpx3 = self.to_complex(dyn_real3, dyn_img3)
        self.dyn_cpx4 = self.to_complex(dyn_real4, dyn_img4)
        self.tsl = tsl
        assert (
            self.dyn_cpx1.shape
            == self.dyn_cpx2.shape
            == self.dyn_cpx3.shape
            == self.dyn_cpx4.shape
        )

        self.dict_path = dic
        self.load_dict()
        self.rmpfsl = self.cal_rmpfsl(
            self.dyn_cpx1, self.dyn_cpx2, self.dyn_cpx3, self.dyn_cpx4, self.tsl
        )
        self.B1_map = loadData(B1_map, "dicom_data")
        self.B1_map = transform.resize(self.B1_map, self.dyn_cpx1.shape)

    def load_dict(self):
        mat_dic = io.loadmat(self.dict_path)
        self.var_MPF = mat_dic["var_MPF"][0]
        self.jtmt = mat_dic["jtmt"]
        self.inhom_b1 = mat_dic["inhom_b1"][0]

    def cal_rmpfsl(self, dyn1, dyn2, dyn3, dyn4, tsl=-0.050):
        nonzero_divide = np.divide(
            np.abs(dyn1 - dyn2),
            np.abs(dyn3 - dyn4),
            out=np.zeros(dyn1.shape),
            where=(dyn3 - dyn4 != 0),
        )
        nonzero_log = np.log(
            nonzero_divide, out=np.zeros_like(nonzero_divide), where=nonzero_divide != 0
        )
        cal_rmpfsl = np.abs(nonzero_log / tsl)
        print(tsl)
        return cal_rmpfsl

    def to_complex(self, real_path, imginary_path):
        real_dcm_data = loadData(real_path, "dicom_data")
        imginary_dcm_data = loadData(imginary_path, "dicom_data")
        return real_dcm_data + 1j * imginary_dcm_data

    def cal_mpf(self):
        h, w = self.rmpfsl.shape
        mpf = np.zeros((w, h))
        for y in range(h):
            for x in range(w):
                b1_check = np.abs(self.B1_map[y, x] - self.inhom_b1)
                num_b1 = np.argmin(b1_check)
                if self.rmpfsl[y, x] > 0 and self.rmpfsl[y, x] < 100:
                    y_check = np.abs(self.rmpfsl[y, x] - self.jtmt[num_b1, :])
                    num_fc = np.argmin(y_check)
                    mpf[y, x] = self.var_MPF[num_fc]
        return mpf


if __name__ == "__main__":
    dict_path = "proc_dict4MPF_liver.mat"
    B1_path = "../samples/0005_B1 map/I0110.dcm"

    dyn_real1 = "../samples/0005_dyn_dicom/I0050.dcm"
    dyn_real2 = "../samples/0005_dyn_dicom/I0060.dcm"
    dyn_real3 = "../samples/0005_dyn_dicom/I0070.dcm"
    dyn_real4 = "../samples/0005_dyn_dicom/I0080.dcm"

    dyn_img1 = "../samples/0005_dyn_dicom/I0090.dcm"
    dyn_img2 = "../samples/0005_dyn_dicom/I0100.dcm"
    dyn_img3 = "../samples/0005_dyn_dicom/I0110.dcm"
    dyn_img4 = "../samples/0005_dyn_dicom/I0120.dcm"

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
    )
    mpf = mpfsl.cal_mpf()

    plt.imshow(mpf, cmap="gray")
    plt.title("MPF_ours")
    plt.show()
