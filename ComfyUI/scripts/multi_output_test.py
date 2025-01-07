

def output_2diff_contrast(data, ratio=1.1):
    print(f"Plugin start")
    ratio1 = ratio
    ratio2 = ratio ** ratio1 
    print(f"Output {ratio1}, {ratio2}")
    return data * ratio1, data * ratio2


def output_3diff_contrast(data, ratio=1.1):
    print(f"Plugin start")
    ratio1 = ratio
    ratio2 = ratio ** ratio1 
    ratio3 = ratio ** ratio2 
    print(f"Output {ratio1}, {ratio2}")
    return data * ratio1, data * ratio2, data * ratio3


