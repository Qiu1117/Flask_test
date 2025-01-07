import numpy as np
from skimage.filters import gaussian
import logging
import time
import pandas as pd
from pandas import DataFrame as df

fake_data = {'diagnostics_Image-original_Mean_x': {'patient0000': 111.44027712950464, 'patient0001': 110.20641491541213, 'patient0002': 66.89770163295982, 'patient0003': 180.27071755704543, 'patient0004': 92.08731168202448, 'patient0005': 131.65722729839524, 'patient0006': 89.70667596487684, 'patient0007': 48.39337132560222, 'patient0008': 126.54101573176575, 'patient0009': 168.41361197327052}, 'diagnostics_Image-original_Maximum_x': {'patient0000': 2972.832967032953, 'patient0001': 3017.4549450549443, 'patient0002': 3740.593162393153, 'patient0003': 5021.471062271041, 'patient0004': 3125.107692307685, 'patient0005': 3833.1604395604127, 'patient0006': 2625.599999999995, 'patient0007': 2301.199999999992, 'patient0008': 2904.7277167277075, 'patient0009': 4117.741147741128}, 'diagnostics_Mask-original_VoxelNum_x': {'patient0000': 678215.0, 'patient0001': 686967.0, 'patient0002': 1546781.0, 'patient0003': 1074964.0, 'patient0004': 857937.0, 'patient0005': 1026706.0, 'patient0006': 739724.0, 'patient0007': 824781.0, 'patient0008': 1005079.0, 'patient0009': 703683.0}, 'diagnostics_Mask-corrected_VoxelNum_x': {'patient0000': 678215.0, 'patient0001': 686967.0, 'patient0002': 1546781.0, 'patient0003': 1074964.0, 'patient0004': 857937.0, 'patient0005': 1026706.0, 'patient0006': 739724.0, 'patient0007': 824781.0, 'patient0008': 1005079.0, 'patient0009': 703683.0}, 'diagnostics_Mask-corrected_Mean_x': {'patient0000': 0.9786684290738242, 'patient0001': 0.9390404812143304, 'patient0002': 0.5038718731594963, 'patient0003': 0.5747092178832802, 'patient0004': 1.0475090493650792, 'patient0005': 0.6373058957112262, 'patient0006': 1.0233047864599425, 'patient0007': 0.3869687979963341, 'patient0008': 1.0602778646983595, 'patient0009': 1.1046046572384751}, 'diagnostics_Mask-corrected_Minimum_x': {'patient0000': -0.481039146660787, 'patient0001': -0.5369068466984054, 'patient0002': -0.5305564789818465, 'patient0003': -0.609001759890724, 'patient0004': -0.4791995765096972, 'patient0005': -0.574561104352648, 'patient0006': -0.5235153046069936, 'patient0007': -0.5403674267883113, 'patient0008': -0.5667462007950901, 'patient0009': -0.5356719285216514}, 'diagnostics_Mask-corrected_Maximum_x': {'patient0000': 5.460845263304564, 'patient0001': 8.755309942516295, 'patient0002': 6.600840297571008, 'patient0003': 9.21335801720134, 'patient0004': 8.07192672897407, 'patient0005': 5.909921879872101, 'patient0006': 9.99091134402174, 'patient0007': 5.577616879853768, 'patient0008': 8.691836656850485, 'patient0009': 8.578934753135126}, 'original_shape_Elongation_x': {'patient0000': 0.7163516953191778, 'patient0001': 0.7002049080503702, 'patient0002': 0.7142042740647385, 'patient0003': 0.7079734804348101, 'patient0004': 0.6993508870392616, 'patient0005': 0.6460203508684969, 'patient0006': 0.5094024257327922, 'patient0007': 0.5604511830885274, 'patient0008': 0.8615661997371327, 'patient0009': 0.7477399690764917}, 'original_shape_Flatness_x': {'patient0000': 0.5105153470644692, 'patient0001': 0.4715209806485361, 'patient0002': 0.606362760588588, 'patient0003': 0.5683946362146948, 'patient0004': 0.5080663643191227, 'patient0005': 0.5688060818592865, 'patient0006': 0.3226115837694888, 'patient0007': 0.4218118026084554, 'patient0008': 0.5904548105443683, 'patient0009': 0.5249423406194703}, 'original_shape_LeastAxisLength_x': {'patient0000': 91.19901145424932, 'patient0001': 85.07786756233483, 'patient0002': 133.6796906408324, 'patient0003': 111.23143913581885, 'patient0004': 101.09115004371382, 'patient0005': 118.0158893598998, 'patient0006': 75.04504767527175, 'patient0007': 99.56751123630168, 'patient0008': 105.89209741096008, 'patient0009': 93.1474072694006}}
fake_data = df(fake_data)

# a = pd.read_csv("liver_spleen_features.csv", index_col='id')
# b = a.iloc[:10, :10]
# b = b.to_dict()



def obtain_df(data):
    return fake_data

def obtain_df_no_data():
    return fake_data, fake_data.to_html()

def get_data(data, row=0, col=0):
    row = int(row) if row.isnumeric() else row
    col = int(col) if col.isnumeric() else col
    
    if type(row) == int:
        return data.iloc[int(row)][col]
    else:
        return data.loc[row][col]


if __name__ == "__main__":
    a = get_data(fake_data, 'patient0001', '9')
    print(a)
