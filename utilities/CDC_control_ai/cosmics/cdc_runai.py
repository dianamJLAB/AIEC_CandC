# Copyright 2020, Jefferson Science Associates, LLC.
# Subject to the terms in the LICENSE file found in the top-level directory.

import mlflow
import numpy as np
import argparse
from sklearn.preprocessing import StandardScaler
import os, sys
from pickle import dump
from pickle import load
from sklearn.gaussian_process import GaussianProcessRegressor
import warnings
from typing import Dict

warnings.filterwarnings("ignore")

def predict_gcf(
    gp_model: GaussianProcessRegressor,
    model_params: Dict,
    model_inputs: Dict = {'pressure':100.5,'temp':299.4,'current':9.0}
): #-> tuple[float, float, dict]:
    """
    Uses the gp_model to predict the gcf and stdv of the prediction for the model_inputs
    
    :param gp_model: Required, the sklearn Gaussian Process Regression model
    
    :param model_params: Required a Dict of the scalars for the inputs and output, and the mean_gcf for inverse scaling the stdv
    
    :param model_inputs: Optional, the keys for the dict are pressure, temp and current. The defaults are pressure: 100.5, temp: 299.4, and current 9.0
    If model_inputs = {'badepics': 1}, then gcf = 0 and stdv = 0 and model_inputs is returned. Essentially, if bad epics are passed in, a prediction is NOT made.
    
    :return: tuple of predicted gcf and stdv for the prediction, and a dictionary of the inputs
    
    .. code-block:: python
        :caption: Example

        import cdc_loadmodel as loadmodel
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.preprocessing import StandardScaler
        
        import cdc_runai as runai
        gcf, gcf_stdv = runai.predict_gcf(gp_model, model_params, model_inputs)
        print('GCF: ', gcf)
        print('STDV: ', gcf_stdv)
        
        # expected output will be:
        GCF: 0.156
        STDV: 0.002
      
    """
    current_feature = ''
    current_scaler = ''
    scaled_inputs = {}
    lst_scaled_vars = []
    
    gcf = 0.141
    stdv = 0.01
    
    # do not do a prediction if "badepics" are passed in
    if "badepics" in model_inputs:
        return gcf, stdv, model_inputs
    
    try:
        input_scalers = ['PRESSURE_MEAN', 'D1_MAX', 'SUM_D1_MAX_MEAN_A_MEAN']
        input_features = ['pressure', 'temp', 'current']
        for input_feature, input_scaler in zip(input_features, input_scalers):
            #track the current feature and scaler for error handling
            current_feature = input_feature
            current_scaler = input_scaler
            
            # get the scalaer
            scaler = model_params[input_scaler]
            var = model_inputs[input_feature]
            # if the input feature is current, then we need to sum temp and current - that sum is what the model uses as the third input parameter
            if (input_feature == 'current'):
                var += model_inputs['temp']
            
            # scale the variable
            var_scaled = scaler.transform(np.asarray(var).reshape(1, -1))
            # add to the input dict
            scaled_inputs[input_scaler] = var_scaled[0][0]
            lst_scaled_vars.append(var_scaled[0][0])

    except:
        print(f'Unable to scale the inputs. Errored on input: {current_feature}, and scaler: {current_scaler}')
    
   
    # use the model to predict the gcf
    #try:
    # make a prediction
    pred_gcf_stdv = gp_model.predict([lst_scaled_vars], return_std=True)
   
        
 
    
    # set the defaults
    gcf = [0.141]
    stdv = [-1]
    
    try:
        # inverse scale the prediction and stdv
        # inverse scale the prediction & stdv
        # prediction: GCF
        pred_gcf = pred_gcf_stdv[0][:]
        # get the GCF scaler
        scaler_GCF = model_params['GAIN']
        gcf = scaler_GCF.inverse_transform(pred_gcf)

        # if stdv was returned, then inverse scale it
        if len(pred_gcf_stdv) > 1:
            # stdv/uncertainty
            pred_stdv = pred_gcf_stdv[1][:].reshape(1, -1)
            #print("Scaled GCF STDV: " + pred_stdv)
            # inverse scale the stdv
            # need to subtract the train_y: hard code the mean GCF for the 2020 data. Need this to inverse scale the stdv
            stdv = scaler_GCF.inverse_transform(pred_stdv) - model_params['MEAN_GCF']
        else:
            # prediction did not return standard deviation
            stdv = [-1]
    except:
        print('Unable to inverse scale the prediction and stdv.')
    
 
    if len(gcf) == 1:
        gcf = gcf[0][0]
    
    if len(stdv) == 1:
        stdv = stdv[0][0]
    
    # returning predicted gain correction factor (gcf), the standard deviation, and the initial model inputs
    #   - model_inputs is a dictionary of the inputs and is returned for ease of logging and debugging
    return gcf, stdv, model_inputs