import numpy as np

def output_2diff_contrast_with_bool(data, ratio=1.1, only_one=False):
    if only_one:
        print(f"Plugin start. Only output one data")
        ratio1 = ratio
        print(f"Output {ratio1}")
        return data * ratio1, np.zeros_like(data)
    else:
        print(f"Plugin start. Output two data")
        ratio1 = ratio
        ratio2 = ratio ** ratio1 
        print(f"Output {ratio1}, {ratio2}")
        return data * ratio1, data * ratio2




