# File: smooth.py
# Project: buildDICOM_dataset
# Created Date: Th Oct 2023
# Author: Qiuyi Shen
# --------------------------------------------------------------------------
# Last Modified: Fri Oct 06 2023
# Modified By: Jiabo Xu
# Version = 1.0
# Copyright (c) 2022 CUHK

import cv2
import matplotlib.pyplot as plt


def gaussian_blur(image):
    kernel_size = (5, 5)
    sigma = 1.0
    gaussian_kernel = cv2.getGaussianKernel(kernel_size[0], sigma)
    gaussian_kernel = gaussian_kernel * gaussian_kernel.T
    smoothed_image = cv2.filter2D(image, -1, gaussian_kernel)
    # plt.subplot(121), plt.imshow(image, cmap="gray"), plt.title("Original")
    # plt.subplot(122), plt.imshow(smoothed_image, cmap="gray"), plt.title("Smoothed")
    # Smooth_diff = image - smoothed_image
    # plt.imshow(Smooth_diff, cmap="gray"), plt.title("Smooth_diff")
    # plt.show()
    return smoothed_image
