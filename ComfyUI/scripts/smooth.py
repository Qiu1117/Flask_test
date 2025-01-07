import numpy as np
from skimage.filters import gaussian
import logging
import time

def smooth_2d(data, sigma=0.3):
    start = time.time()
    print(f"Smooth start with Sigma={sigma}")
    data = gaussian(data, sigma, preserve_range=True)
    print(f"It takes {time.time() - start} sec")
    return data, "this is a text output"


def smooth_3d(data, sigma=0.3):
    start = time.time()
    print(f"Smooth start with Sigma={sigma}")
    data = gaussian(data, sigma, preserve_range=True)
    print(f"It takes {time.time() - start} sec")
    return data, "this is a text output"


