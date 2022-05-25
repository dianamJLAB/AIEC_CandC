# AIEC_CandC

## AI for Experiment Controls Project

For the first time, the Jefferson Lab [GlueX](http://www.gluex.org/) Central Drift Chamber was autonomously calibrated and controlled using machine learning while recording cosmic ray tracks. A Gaussian Process (GP), implemented using the scikit-learn library, was trained to predict the gain correction factor and to inform a high voltage setting that will stabilize the CDC gain in response to changing environmental conditions. Using ML to perform near real time calibrations significantly reduces the required computing resources typically used in the traditional, post hoc calibration process. 

## The Repo Contains:

### D-data-CDC directory:
contains csv data files used for training, test, and evaluation of the GP
* 2020_GCF_All.csv: features and target for 2020 runs
* 2021_2020_GCF_All.csv: features and target for 2020 and 2021 runs
* Balanced_2020_GCF_Test.csv: pressure-balanced test data set of 2020 runs
* Balanced_2020_GCF_Train.csv: pressure-balanced train data set of 2020 runs
* Balanced_2021_2020_GCF_Test.csv: pressure-balanced test data set of 2020 and 2021 runs
* Balanced_2021_2020_GCF_Train.csv: pressure-balanced train data set of 2020 and 2021 runs
* preds_sklearnGPR_Trained20202021.csv: features, targets, and predictions for 2020, 2021 data
* preds_withstdv.csv: features, targets, and predictions for range of pressure and current with temp set to 299.4
* surface_plot_data_big_2.csv: created features for range of pressures, temp and currents to use for model evaluation.
