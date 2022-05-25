import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C, RationalQuadratic as RQ, WhiteKernel, ExpSineSquared as Exp, DotProduct as Lin

from pickle import dump

class GPR_SkLearn():
    def __init__(self, 
                train_data_X,
                train_data_y, 
                train_iterations = 20,
                kernel_list = [RBF(length_scale=1.0, length_scale_bounds=(1e-3, 1e3)), WhiteKernel(noise_level=1e-1, noise_level_bounds=(1e-5, 1e1))],
                verbose = False,
                ):

        self.train_data_X = train_data_X # train data inputs
        self.train_data_y = train_data_y # train data output
        self.train_iterations = train_iterations
        self.kernel_list = kernel_list
        self.verbose = verbose

        # explicitly setting class attributes to None that get set after calling train_model()
        self.model = None

        if self.verbose:
            print('Created GPR_SkLearn class.')

    def train_model(self):

        
        kernel = RBF() + WhiteKernel()

        self.model = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=self.train_iterations, random_state=0)
        self.model.fit(self.train_data_X, self.train_data_y)

        return self.model

    def predict(self, test_data_X):
        # predictions and stdvs
        preds_and_stdv = self.model.predict(test_data_X, return_std=True)
       
        # predictions
        preds = preds_and_stdv[0][:]

        # stdv/uncertainty
        stdvs = (preds_and_stdv[1][:]).reshape(-1, 1) 
        
        return preds, stdvs
