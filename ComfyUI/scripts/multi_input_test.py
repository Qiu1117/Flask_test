import time


def add_2data_together(data1, data2, ratioA=0.5):
    start = time.time()
    print(f"Plugin start")
    data = (1 - ratioA) * data1 + ratioA * data2
    print(f"It takes {time.time() - start} sec")
    return data


def add_3data_together(data1, data2, data3, ratioA=0.33, ratioB=0.33):
    start = time.time()
    print(f"Plugin start")
    data = (1 - ratioA - ratioB) * data1 + ratioA * data2 + ratioB * data3
    print(f"It takes {time.time() - start} sec")
    return data


