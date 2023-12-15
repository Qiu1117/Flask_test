# -*- coding: utf-8 -*-
"""
Created on Tue Dec 21 11:44:06 2021

@author: Chaoxing Huang, DIIR, CUHK
@author: Jiabo Xu, DIIR, CUHK

Implementation was based on  mannual  and matlab implementation of Professor Thierry Blu, 
EE,CUHK
"""

import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt
from typing import Union, List


from QMR.utils import loadData


class ab_fitting:
    def __init__(self, fsl:List[int], dyn_scans:List[str]):
        assert len(fsl) > 1
        assert len(fsl) == len(dyn_scans)

        self.x = np.expand_dims(np.array(fsl), axis=(1,2))
        self.y = np.array([loadData(x,'dicom_data') for x in dyn_scans])


    def _compute_J(self, b,x,y):
        '''
        Parameters
        ----------
        b : np array
            H X W
        x : np array, time of spin-lock
            NTSL X h x w
        y : np array, multiple dynamic scans
            NTSL X h x w

        Returns
        -------
        J : np array, cost function value corresponds to every pixels 
            h  x w 

        '''
        # Implementation accroding to Thierry's manuual 
        f1 = np.mean(y*np.exp(-b*x),axis=0)
        alpha1 = np.mean(np.exp(-b*x),axis=0)
        alpha2 = np.mean(np.exp(-2*b*x),axis=0)
        f0 = np.mean(y,axis=0)
            
        a = (f1-alpha1*f0)/(alpha2-alpha1**2)
        L = np.abs(y-a*np.exp(-b*x))
        J = np.sum(L**2,axis=0)
        
        return J


    def fit(self):
        '''
        Parameters
        ----------
        x : np array, time of spin-lock
            NTSL X h x w
        y : np array, multiple dynamic scans
            NTSL X h x w

        Returns T1rho
        -------
        
        '''
        bmin=1e-5*np.ones_like(self.y[0])   
        bmax = 1e5*np.ones_like(self.y[0])   
        eps = 1e-9
        count =0
        while(1):
            # Dichotomic algorithm. 
            b = (bmin+bmax)/2
            dJ = self._compute_J(b+eps, self.x, self.y) - self._compute_J(b, self.x, self.y)
            pos_idx = np.where(dJ>=0)
            neg_idx = np.where(dJ<0)
            bmax[pos_idx]=b[pos_idx]
            bmin[neg_idx]=b[neg_idx]
            
            interval_length = np.abs(bmax-bmin)
            count+=1
            if np.linalg.norm(interval_length)<1e-3:
                break
            elif count>1000:
                print('take too long,break!')
                break
        return 1/(b+1e-9)   # we are computing R1rho, we need to invert R1rho to t1rho


if __name__=='__main__':
    image_list = ['../samples/t1rho_test/dicom/I0010.dcm',
                  '../samples/t1rho_test/dicom/I0020.dcm',
                  '../samples/t1rho_test/dicom/I0030.dcm',
                  '../samples/t1rho_test/dicom/I0040.dcm']
    
    t1rho = ab_fitting([0, 0.01, 0.03, 0.05], image_list)
    res = t1rho.fit()

    plt.figure(1)
    plt.imshow(res, vmin=0.02, vmax=0.06,cmap='jet')
    plt.colorbar()
    plt.show()    
