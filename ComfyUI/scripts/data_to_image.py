from skimage import io
import numpy as np

def main(data, filename, normalize=True):
    filename = str(filename) + '.png'
    if type(data) != np.ndarray:
        raise ValueError("Data must be a numpy array")
    if data.max() > 255 or data.min() < 0:
        data = (data - data.min()) / (data.max() - data.min()) * 255
    else:
        if normalize:
            data = (data - data.min()) / (data.max() - data.min()) * 255

    io.imsave(filename, data.astype(np.uint16))