import numpy as np



def getAutoCorrelation(x):
    lags = np.arange(len(x))

    '''numpy.corrcoef, partial'''
    corr=[1. if l==0 else round(np.corrcoef(x[l:],x[:-l])[0][1], 4) for l in lags]
    auto_corr = np.array(corr)

    """Trimming off 3% initial and last data"""
    per_3_data = int(len(auto_corr)*0.03)
    rest_97_data = auto_corr[per_3_data:-per_3_data]

    return rest_97_data