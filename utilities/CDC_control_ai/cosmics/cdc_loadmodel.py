import mlflow
import mlflow.pyfunc
import numpy as np
import argparse
from sklearn.preprocessing import StandardScaler
import os, sys
import pickle
from sklearn.gaussian_process import GaussianProcessRegressor
import warnings
from typing import Dict, List, Optional
from mlflow.tracking import MlflowClient
import re

warnings.filterwarnings("ignore")

def load_model(
    model_name: str = '',
    exact_model: Optional[str] = 'Production',
    
): #-> tuple[GaussianProcessRegressor, Dict]:
    """
    Default behavior retrieves the model from the mlflow server by name. A particular version of Staging or Production for the model can be retrieved with the --exact_model argument
    
    :param model_name: Required, the file path for the model pkl file.
   
    :param exact_model: Optional, str, The default will return the latest version of the Production model. Also can reference a particular version of the model: 'Staging,3' for version 3 of the stages mlflow model, or 'Production,2' for version 2 of the production model. 'Staging' will return the latest version of the staged model.
    
    :return: the compiled model sklearn.gaussian_process.GaussianProcessRegressor, the scalars: [StandardScaler for pressure, StandardScaler for temp, StandardScaler for current+temp, StandardScaler for GCF], and the mean gain correction factor which is needed to inverse scale predictions.
    
    .. code-block:: python

        import cdc_loadmodel as loadmodel
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.preprocessing import StandardScaler
        
        import cdc_loadmodel as loadmodel
        gp_model, params = loadmodel.load_model('/group/data_science/blah/blah/blah/model.pkl')
        print(gp_model)
        
        # expected output will be:
        mlflow.pyfunc.loaded_model:
          artifact_path: GPR_GCF
          flavor: mlflow.sklearn
          run_id: 37b80fe1fd314ec6b8bf84048602a961
        
        print(params)
        # expected output will be
        {'D1_MAX': StandardScaler(),
         'GAIN': StandardScaler(),
         'PRESSURE_MEAN': StandardScaler(),
         'SUM_D1_MAX_MEAN_A_MEAN': StandardScaler(),
         'MEAN_GCF': 0.152933}
      
    """
    # set model to none to start
    model = None
    # default mean_gcf
    mean_gcf = 0.14
    #default the model_params to an empty dict
    model_params = {}
    
    
    if len(model_name) == 0: 
        print('You must provide a model_name')
        sys.exit()
    else:
        try:
            # load the GPR model
            # Load from file
            with open(model_name, 'rb') as file:
                model = pickle.load(file)
        except:
            print('Unable to load the model from a filepath: ' + model_name)
            

    # get the file path used for the model file and use for the scalars
    artifacts_uri = model_name.replace(os.path.basename(model_name),'')
    
    # get the mean gcf from the txt file in the same location as the scalars
    with open(os.path.join(artifacts_uri, 'mean_gcf.txt')) as f:
        mean_gcf = f.readline()
            
    
    # FOURTH, grab the 4 scalars I need - just in alpha order
    scaler_names = ['D1_MAX', 'GAIN', 'PRESSURE_MEAN', 'SUM_D1_MAX_MEAN_A_MEAN']
    for scaler_name in scaler_names:
        scaler_filename = 'scalar_' + scaler_name + '.pkl'
        scaler = pickle.load(open(os.path.join(artifacts_uri, scaler_filename), 'rb'))
        model_params[scaler_name] = scaler
    
    
    
    # the mean GCF may be stored as either a string of the float value, or a string about the float = 'GAIN 0.152933 dtype: float64'
    # need to deal with that
    try:
        if mean_gcf.isnumeric():
            mean_gcf = float(mean_gcf)
        else:
            mean_gcf = float(re.findall(r"[-+]?\d*\.?\d+", mean_gcf)[0])
    except:
        # could not grab the mean_gcf. Return -1. as mean_gcf so that calling program and decide how to deal with this
        mean_gcf = -1.
            
    model_params['MEAN_GCF'] = mean_gcf
    
    return model, model_params
   