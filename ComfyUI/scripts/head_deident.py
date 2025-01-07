
# File: de-ident_v8.py
# Project: Ours
# Created Date: We Jul 2022
# Author: Jiabo Xu
# --------------------------------------------------------------------------
# Last Modified: Sat Nov 19 2022
# Modified By: Jiabo Xu
# Version = 1.0
# Copyright (c) 2022 CUHK


"""
DESCRIPTION: 

CHANGES: Simplify input and output

"""
import numpy as np
import nibabel as nib
from skimage import filters, morphology, measure
from scipy import signal
import time
from pathlib import Path
from skimage import filters, morphology
from skimage.draw import disk, ellipsoid
from functools import wraps
from pydicom import dcmread
from pydicom.uid import RLELossless
from pydicom.uid import UID
import sys, json


def exist_or_create(path):
    if not path.exists():
        path.mkdir(exist_ok=True, parents=True)

def get_time(func):
    @wraps(func)
    def inner(*args, **kwargs):
        start_time = time.time()
        res = func(*args, **kwargs)
        end_time = time.time()
        print('the {} running time is {}'.format(func.__name__, (end_time - start_time)))

        return res
    return inner


class head_deidentification:
    def __init__(self, data, modality, organ, threshold=20, thick=3, distort=True):
        self.data = data
        self.width, self.height, self.slice = data.shape

        self.threshold = threshold
        self.thick = thick
        self.distort = distort
        self.sphere_base_size = np.array([5, 5, 10])

        self.modality = modality
        self.organ = organ
        self.lowest = 0 if modality != 'ct' else -1000
        self.getDistribution(self.data)

        self.z_boundary = [0, 0]  
        self.boundaries = []


    def getDistribution(self, data):
        un = np.unique(data)
        low = np.percentile(un, 2)
        up = np.percentile(un, 60)
        self.dist = np.array([x for x in un if x < up and x > low])
        self.weight = None


    def _fillHole(self, data):
        labels = measure.label(data, connectivity=1)
        if labels.max() == 0:
            return labels
        largestCC = np.argmax(np.bincount(labels.flat)[1:])+1
        
        bg = labels==0
        labels[labels!=largestCC] = 0
        labels[bg] = 0
        return labels

    def fillHole(self, data):
        inverse_data = 1 - data.copy()
        inverse_data

        fill_black = self._fillHole(inverse_data)
        fill_black = 1 - fill_black

        fill_white = self._fillHole(fill_black)
        fill_white[fill_white!=0] = 1
        return fill_white
    
    def refineMask(self, mask):
        new_mask = filters.median(mask, morphology.cube(3))
        return new_mask

    def _getBorder(self, data):
        data = data.copy()
        data[data!=0] = 1
        labels = measure.label(data)
        props = measure.regionprops(labels)
        if not props:  # full zero image
            return None 
        else:
            left = min([x.bbox[0] for x in props])
            top = min([x.bbox[1] for x in props])
            right = max([x.bbox[2] for x in props])
            bot = max([x.bbox[3] for x in props])

            return [left, top, right, bot]

    def getMask(self):
        data = self.data.copy()
        
        data[self.data<self.threshold] = 0
        data[self.data>=self.threshold] = 1
        
        # l = []
        # for i in range(200):
        #     data[self.data<i] = 0
        #     data[self.data>=i] = 1
        #     #labels = measure.label(data)
        #     #l.append(labels.max())
        #     s = data.sum()
        #     l.append(s)
        # import matplotlib.pyplot as plt
        # plt.plot(l)
        # plt.show()

        labels = measure.label(data)
        assert( labels.max() != 0 ) # assume at least 1 CC
        largestCC = labels == np.argmax(np.bincount(labels.flat)[1:])+1
        props = measure.regionprops(largestCC.astype(np.uint8))  
        _, _, self.z_boundary[0], _, _, self.z_boundary[1] = props[0].bbox

        largestCC = largestCC.astype(int)

        mask_vol = []
        for i in range(data.shape[2]):
            slice = largestCC[:,:,i]
            if np.all(slice == 0):
                empty_slice = np.zeros_like(largestCC[:,:,i])
                mask_vol.append(empty_slice)
            else:
                bbox = self._getBorder(slice)
                self.boundaries.append(bbox)
                mask = self.fillHole(slice)
                mask[mask!=0] = 1
                mask_vol.append(mask)
            
                
        assert len(self.boundaries) - (self.z_boundary[1] - self.z_boundary[0]) == 0
        mask_vol = np.transpose(np.array(mask_vol), (1,2,0))
        
        return mask_vol


    def getContour(self, mask):
        erosed = morphology.erosion(mask, morphology.cube(self.thick))
        contour = mask - erosed
        return contour, erosed

    def get_one_pixel_contour(self, mask):
        one_pixel_erosion = morphology.erosion(mask, morphology.cube(3))
        one_pixel_contour = mask - one_pixel_erosion
        return one_pixel_contour

        
    def getMidPoint(self, l, r, t, b, z_l, z_r):
        return (r + l) // 2, (b + t) // 2, (z_r + z_l) // 2

    def _getBoundMost(self):
        l_most = min(self.boundaries, key=lambda x:x[0])[0]
        r_most = max(self.boundaries, key=lambda x:x[2])[2]
        t_most = min(self.boundaries, key=lambda x:x[1])[1]
        b_most = max(self.boundaries, key=lambda x:x[3])[3]
        return l_most, r_most, t_most, b_most

    def getValidVolume(self, l, r, t, b, z_l, z_r):
        x_ratio = 1/3
        y_ratio = 1/4
        z_ratio = 1/8
        left = l
        x_mid = (l + r) // 2
        right =  x_mid - int(x_ratio * (x_mid - l))
        top = t + int(y_ratio * (b - t))
        bot = b - int(y_ratio * (b - t))
        z_left = z_l + int(z_ratio * (z_r - z_l))
        z_right = z_r - int(z_ratio * (z_r - z_l))

        offset = (left + self.sphere_base_size[0], top + self.sphere_base_size[1], z_left + self.sphere_base_size[2])
        return self.data.copy()[left:right, top:bot, z_left:z_right], offset  # slice on numpy is not copy

    
    def getOrgans(self):
        cavity_threshold = 50   # should be adaptive
        area_threshold = (1000, 50000) 
        same_row_error = 5
        l_most, r_most, t_most, b_most = self._getBoundMost()
        
        self.mid_points = self.getMidPoint(l_most, r_most, t_most, b_most, *self.z_boundary)
        valid_volume, offset = self.getValidVolume(l_most, r_most, t_most, b_most, *self.z_boundary)
        self.valid_volume = valid_volume

        sphere_kernel = ellipsoid(*self.sphere_base_size, levelset=False)
        valid_volume = (valid_volume - valid_volume.min()) / valid_volume.max() 
        output = signal.convolve(valid_volume, sphere_kernel, mode='valid', method='fft')  
        
        output[output < cavity_threshold] = 1
        output[output >= cavity_threshold] = 0

        labeled_output, num = measure.label(output, connectivity=1, return_num=True)
        
        output_prop = measure.regionprops(labeled_output)

        centroid_dict = {}
        for i, label in enumerate(output_prop, 1):
            if label.area > area_threshold[1] or label.area < area_threshold[0]:
                labeled_output[labeled_output==i] = 0
            else:
                if centroid_dict:
                    finish = False
                    for centroid in centroid_dict.keys():
                        if abs(label.centroid[1] - centroid[1]) <= same_row_error:
                            centroid_dict[centroid].append(label.bbox)
                            #labeled_output[labeled_output == i] = centroid_dict[centroid][0]
                            finish = True
                            break
                    if not finish:
                        centroid_dict[label.centroid] = [label.bbox]
                        #labeled_output[labeled_output == i] = i
                else:
                    centroid_dict[label.centroid] = [label.bbox]
                    #labeled_output[labeled_output == i] = i
                    
        for k in list(centroid_dict):
            if len(centroid_dict[k]) != 2:
                del centroid_dict[k]


        order = sorted(centroid_dict, key=lambda x:x[1])
        self.organ_pos = {'eyes': centroid_dict[order[0]], 'nose': centroid_dict[order[1]]}
        
        self.labeled_organ = labeled_output
        self.organ_mask = output
        self.offset = offset

        assert len(self.organ_pos['eyes']) == 2, len(self.organ_pos['eyes'])
        assert len(self.organ_pos['nose']) == 2, len(self.organ_pos['nose'])


    def randomize_noorgan(self, mask, erosed):
        new_data = self.data.copy()
        mask = mask.copy()
            
        # 0.2 second faster
        random_num_size = int(mask.sum())
        random_num_pool = np.random.choice(self.dist, size=random_num_size, p=self.weight)  
        idx = 0

        for i, z in enumerate(range(self.z_boundary[0], self.z_boundary[1])):
            left, top, right, bot = self.boundaries[i]
            #random_num_pool = np.random.choice(self.dist, size=(right-left)*(bot-top), p=self.weight)
            for y in range(top, bot):
                for x in range(left, right):
                    if mask[x, y, z] == 1:
                        new_data[x, y, z] = random_num_pool[idx] 
                        #new_data[x, y, z] = 0
                        idx += 1        
                    elif mask[x, y, z] == 0 and erosed[x, y, z] == 0:
                        new_data[x, y, z] = self.lowest

        return new_data

    def randomize(self, mask, erosed, organs):
        new_data = self.data.copy()
        mask = mask.copy()
        offset_x, offset_y, offset_z = self.offset
        
        if self.organ_pos['eyes'][0][5] < self.organ_pos['eyes'][1][5]:
            left_eye, right_eye = self.organ_pos['eyes']
        else:
            right_eye, left_eye = self.organ_pos['eyes']
            
        left_eye_x_min = left_eye[0] + offset_x
        left_eye_x_max = left_eye[3] + offset_x
        left_eye_y_min = left_eye[1] + offset_y
        left_eye_y_max = left_eye[4] + offset_y
        left_eye_z_min = left_eye[2] + offset_z
        left_eye_z_max = left_eye[5] + offset_z
        right_eye_x_min = left_eye[0] + offset_x
        right_eye_x_max = left_eye[3] + offset_x
        right_eye_y_min = right_eye[1] + offset_y
        right_eye_y_max = right_eye[4] + offset_y
        right_eye_z_min = right_eye[2] + offset_z + self.sphere_base_size[0]
        right_eye_z_max = right_eye[5] + offset_z + self.sphere_base_size[0]

        if self.organ_pos['nose'][0][5] < self.organ_pos['nose'][1][5]:
            left_sinus, right_sinus = self.organ_pos['nose']
        else:
            right_sinus, left_sinus = self.organ_pos['nose']

        # nose should be between two sinus
        nose_right = left_sinus[0] + offset_x
        nose_top = left_eye[4] + offset_y
        nose_bot = left_sinus[4] + offset_y + 3
        nose_z_min = left_sinus[5] + offset_z
        nose_z_max = right_sinus[2] + offset_z

        # mouth should be below the nose
        mouth_right = nose_right
        mouth_z_min = left_sinus[2] + offset_z
        mouth_z_max = right_sinus[5]+ offset_z
        mouth_top = nose_bot + 5

        # 0.2 second faster
        random_num_size = int(mask.sum())
        random_num_pool = np.random.choice(self.dist, size=random_num_size, p=self.weight)  
        idx = 0

        for i, z in enumerate(range(self.z_boundary[0], self.z_boundary[1])):
            left, top, right, bot = self.boundaries[i]
            #random_num_pool = np.random.choice(self.dist, size=(right-left)*(bot-top), p=self.weight)
            for y in range(top, bot):
                for x in range(left, right):
                    if x < self.width // 2:
                        if left_eye_y_min <= y <= left_eye_y_max and (left_eye_z_min <= z <= left_eye_z_max or right_eye_z_min <= z <= right_eye_z_max): 
                            if organs['eyes'] ==  'keep':
                                continue
                            elif organs['eyes'] == 'remove':
                                new_data[:left_eye_x_max,y,z] = self.lowest
                                mask[:left_eye_x_max,y,z] = 0
                                new_data[:right_eye_x_max,y,z] = self.lowest
                                mask[:right_eye_x_max,y,z] = 0
                            else:
                                pass
                        elif nose_top <= y <= nose_bot and nose_z_min <= z <= nose_z_max:
                            if organs['nose'] ==  'keep':
                                continue
                            elif organs['nose'] == 'remove':
                                new_data[:nose_right,y,z] = self.lowest
                                mask[:nose_right,y,z] = 0
                            else:
                                pass
                        elif mouth_top <= y  and mouth_z_min <= z <= mouth_z_max:
                            if organs['mouth'] ==  'keep':
                                continue
                            elif organs['mouth'] == 'remove':
                                new_data[:mouth_right,y,z] = self.lowest
                                mask[:mouth_right,y,z] = 0
                            else:
                                pass
                    if mask[x, y, z] == 1:
                        new_data[x, y, z] = random_num_pool[idx]       
                        idx += 1        
                    elif mask[x, y, z] == 0 and erosed[x, y, z] == 0:
                        new_data[x, y, z] = self.lowest

        return new_data


    def deface(self, mask, erosed):
        new_data = self.data.copy()
        offset_x, offset_y, offset_z = self.offset
        all_region = [v for x in self.organ_pos.values() for v in x]
        
        right_most = self.organ_pos['eyes'][0][3] + offset_x
        top_most = min(all_region, key=lambda x:x[1])[1] + offset_y

        random_num_size = int(mask.sum())
        random_num_pool = np.random.choice(self.dist, size=random_num_size, p=self.weight)
        idx = 0
        for i, z in enumerate(range(self.z_boundary[0], self.z_boundary[1])):
            left, top, right, bot = self.boundaries[i]
            #random_num_pool = np.random.choice(self.dist, size=(right-left)*(bot-top), p=self.weight)
            for y in range(top, bot):
                for x in range(left, right):
                    if mask[x, y, z] == 1:
                        new_data[x, y ,z] = random_num_pool[idx]
                        idx += 1                    
                    elif mask[x, y, z] == 0 and erosed[x, y, z] == 0:
                        new_data[x, y, z] = self.lowest
        new_data[:right_most, top_most:, :] = self.lowest
        return new_data


    def face_only(self, mask, erosed):
        new_data = self.data.copy()
        offset_x, offset_y, offset_z = self.offset
        all_region = [v for x in self.organ_pos.values() for v in x]
        
        right_most = self.organ_pos['eyes'][0][3] + offset_x
        top_most = min(all_region, key=lambda x:x[1])[1] + offset_y

        random_num_size = int(mask.sum())
        random_num_pool = np.random.choice(self.dist, size=random_num_size, p=self.weight)  

        idx = 0
        for i, z in enumerate(range(self.z_boundary[0], self.z_boundary[1])):
            left, top, right, bot = self.boundaries[i]
            for y in range(top_most, bot):
                for x in range(left, right_most):
                    if mask[x, y, z] == 1:
                        new_data[x, y, z] = random_num_pool[idx]       
                        idx += 1        
                    elif mask[x, y, z] == 0 and erosed[x, y, z] == 0:
                        new_data[x, y, z] = self.lowest

        # update contour
        temp = np.zeros_like(mask)
        temp[:right_most, top_most:, :] = 1
        self.contour *= temp

        return new_data


    def getDistortedMask(self, mask, outline):
        width, height, _ = self.data.shape

        idx = 0
        random_num_size = int(outline.sum())
        random_num_pool = np.random.randint(0, 100, random_num_size)
        random_thick_pool = np.random.randint(1, self.thick, random_num_size)

        for i, z in enumerate(range(self.z_boundary[0], self.z_boundary[1])):
            left, top, right, bot = self.boundaries[i]
            for y in range(top, bot):
                for x in range(left, right):
                    if outline[x,y,z] == 1:
                        if random_num_pool[idx] < 10:
                            random_radius = random_thick_pool[idx]
                            rr, cc = disk((x, y), random_radius)
                            rr[rr >= width] = 0
                            cc[cc >= height] = 0
                            mask[rr, cc, z] = 0
                        idx += 1

        distorted_mask = filters.gaussian(mask, sigma=0.1)

        threshold = np.percentile(distorted_mask, 25)
        distorted_mask[distorted_mask>threshold] = 1
        distorted_mask[distorted_mask<=threshold] = 0

        return distorted_mask

    def getDiff(self, mask, data, new_data):
        mask = mask.copy()
        mask[mask > 0 ] = 1
        mask = 1 - mask
        diff = np.absolute(new_data * mask - data) 
        return diff
    

    def view(self):
        diff = self.getDiff(self.contour, self.data, self.new_data)
        return {'mask': self.mask.astype(np.int16),
                'refined_mask': self.refined_mask.astype(np.int16),
                'contour': self.contour.astype(np.int16),
                'diff': diff,
                'data': self.new_data}


    def output(self):
        return self.new_data


    def pipeline(self):
        self.mask = self.getMask()
        print('Obtained the head mask')

        #self.random_size = self.getRandomNums()
        if self.modality != 'ct' and not (self.organ['eyes'] == 'blur' and self.organ['mouth'] == 'blur' and self.organ['nose'] == 'blur'):
            self.getOrgans()
        print('Obtained the organ position')
        self.refined_mask = self.refineMask(self.mask)
        
        if self.distort:
            self.one_pixel_contour = self.get_one_pixel_contour(self.refined_mask)
            self.distort_mask = self.getDistortedMask(self.refined_mask, self.one_pixel_contour)
            self.contour, self.erosed = self.getContour(self.distort_mask)
        else:
            self.contour, self.erosed = self.getContour(self.refined_mask)

        print('Start randomization')
        if self.modality != 'ct' and (self.organ['eyes'] != 'blur' and self.organ['mouth'] != 'blur' and self.organ['nose'] != 'blur'):
            if self.organ == 'face':
                self.new_data = self.deface(self.contour, self.erosed)
            elif self.organ == 'face_only':
                self.new_data = self.face_only(self.contour, self.erosed)
            else:
                self.new_data = self.randomize(self.contour, self.erosed, self.organ)
        else:
            self.new_data = self.randomize_noorgan(self.contour, self.erosed)
            #self.new_data = self.randomize(self.contour, self.erosed, self.organ)
        print('Algorithm finished')


def create_affine(dicom_path, path_mode=True):
    if path_mode:
        dicom_lists = list(dicom_path.glob('*.dcm'))  # suppose they are named and sorted correctly
        first_sample = dcmread(dicom_lists[0], force=True)
        last_sample = dcmread(dicom_lists[-1], force=True)
        dicom_amount = len(dicom_lists)
    else:
        first_sample = dicom_path[0]
        last_sample = dicom_path[-1]
        dicom_amount = len(dicom_path)

    image_orient1 = np.array(first_sample.ImageOrientationPatient)[0:3]
    image_orient2 = np.array(first_sample.ImageOrientationPatient)[3:6]

    #slice_space = float(first_sample.SpacingBetweenSlices)  # not accurate compared with current method of step calculation 
    delta_r = float(first_sample.PixelSpacing[0])
    delta_c = float(first_sample.PixelSpacing[1])

    image_pos = np.array(first_sample.ImagePositionPatient)
    last_image_pos = np.array(last_sample.ImagePositionPatient)
    step = (image_pos - last_image_pos) / (1 - dicom_amount)

    affine = np.matrix([[-image_orient1[0] * delta_c, -image_orient2[0] * delta_r, -step[0], -image_pos[0]],
                        [-image_orient1[1] * delta_c, -image_orient2[1] * delta_r, -step[1], -image_pos[1]],
                        [image_orient1[2] * delta_c, image_orient2[2] * delta_r, step[2], image_pos[2]],
                        [0, 0, 0, 1]])
    return affine


def obtain_paths(path):
    path = Path(path)
    if '.json' in path.suffixes:
        with open(path, 'r') as f:
            paths = json.load(f)
    else:
        paths = list(path.glob('*'))
    return paths


def load_dcm_series(path):
    paths = obtain_paths(path)
    dcm_list = []
    name_list = []
    for p in paths: # assume data under the path are from same series
        try:
            dc = dcmread(p, force=True)
        except:
            continue  # pass non dicom data
        name = Path(p).stem
        name_list.append(name)
        if hasattr(dc, 'InstanceNumber'):
            dcm_list.append(dc)
    dcm_list = sorted(dcm_list, key=lambda x: int(x.InstanceNumber))
    try:            
        volume = np.array([dcm.pixel_array for dcm in dcm_list]).transpose((2,1,0)) 
    except ValueError:
        print('ERROR!!! The folder is not a standard input of head de-identification')
        sys.exit()

    return volume, dcm_list, name_list


def output_dcm(volume, output_root, dcm_list, name_list, compress):
    volume = volume.transpose((2,1,0))
    for i, dcm in enumerate(dcm_list):
        deidentified = np.ascontiguousarray(volume[i])
        if UID(dcm.file_meta.TransferSyntaxUID).is_compressed or compress:
            dcm.compress(RLELossless, deidentified)
        else:
            dcm.PixelData = deidentified
        dcm.save_as(Path(output_root) / f"{name_list[i]}.dcm")


def store_nii(data, name, affine):
    nib.save(nib.Nifti1Image(data, affine), f'{name}.nii.gz')

#@get_time
def execution(head_data, modality='mr', threshold=20, thick=3, distort=False, organ_eyes='blur', organ_nose='blur', organ_mouth='blur'):
    '''
        Head-de-identification for MR 3D T1w Head scan of Sagittal view images.
        :param series_path: the folder path of a complete series
        :param output_root: the output folder path to store either nifti for view or dicoms as original input structures and names.
        :param mode: valid input are 'view' for display the process and 'store' for save the de-identified data. Default: view
    '''
    organ={'eyes':organ_eyes, 'nose':organ_nose, 'mouth':organ_mouth}
    volume = head_data
    de_ident = head_deidentification(volume, modality, organ, threshold, thick, distort)
    de_ident.pipeline()
    #deident_outcome = de_ident.output()
    view = de_ident.view()
    return view['data'], view['mask'], view['refined_mask'], view['contour'], view['diff'] 

def execution_debug(head_data, modality='mr', threshold=20, thick=3, distort=False, organ_eyes='blur', organ_nose='blur', organ_mouth='blur'):
    '''
        Head-de-identification for MR 3D T1w Head scan of Sagittal view images.
        :param series_path: the folder path of a complete series
        :param output_root: the output folder path to store either nifti for view or dicoms as original input structures and names.
        :param mode: valid input are 'view' for display the process and 'store' for save the de-identified data. Default: view
    '''
    #deident_outcome = de_ident.output()
    print(f"Finish Execution Head De-identification on parameters: {modality}, {threshold}, {thick}, {distort}, {organ_eyes}, {organ_nose}, {organ_mouth}")
    return  head_data + 10, head_data + 100, head_data + 1000, head_data + 10000, head_data + 100000

def folder2json(folder_path, output_json):
    with open(output_json, 'w') as f:
        json.dump([str(p) for p in Path(folder_path).glob('*.dcm')], f)


# if __name__ == '__main__':
#     nifti = nib.load('test.nii.gz')    
#     n = execution(nifti)
#     print(n)