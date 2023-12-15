# %% base import
import matplotlib.pyplot as plt
import numpy as np
import nibabel as nib
from QMR.smooth.gaussian_blur import gaussian_blur
import pydicom


# %% MPFSL
from QMR.MPFSL import MPFSL

colorbar = None


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
    dyn_real2 = realctr[0]
    dyn_real3 = realctr[1]
    dyn_real1 = realctr[2]
    dyn_real4 = realctr[3]

    dyn_img1 = ictr[0]
    dyn_img2 = ictr[1]
    dyn_img3 = ictr[2]
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

    image_path = r"C:\Users\Qiuyi\Desktop\uploads\mpf\Mpf_output.jpg"
    plt.imshow(mpf, cmap="jet")
    if colorbar is None:
        # 只在第一次调用时生成颜色条
        colorbar = plt.colorbar()
    else:
        # 其他调用时不生成新的颜色条
        plt.colorbar(cax=colorbar.ax)
    # plt.colorbar()
    plt.savefig(image_path, format="jpeg", dpi=300, bbox_inches="tight")

    ds = pydicom.dcmread(dyn_real1)
    ds.PixelData = mpf_result.tobytes()
    rows, columns = mpf_result.shape
    ds.Rows = rows
    ds.Columns = columns

    min_val = np.min(mpf_result)
    max_val = np.max(mpf_result)
    window_width = max_val - min_val
    window_level = (max_val + min_val) / 2

    ds.WindowWidth = window_width
    ds.WindowCenter = window_level
    # imagetype
    ds.SamplesPerPixel = 1  # 对于灰度图像，每个像素只包含一个样本
    ds.BitsAllocated = 16  # 每个样本使用16位进行编码
    ds.BitsStored = 16  # 每个样本使用16位进行存储
    ds.HighBit = 15  # 最高有效位为第15位
    ds.RescaleIntercept = 0
    ds.RescaleSlope = 1

    output_dicom_path = r"C:\Users\Qiuyi\Desktop\uploads\mpf\Mpf_output.dcm"
    ds.save_as(output_dicom_path)

    return


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
