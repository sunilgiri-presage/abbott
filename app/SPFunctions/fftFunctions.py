import numpy as np
from scipy.fftpack import fft,ifft
import math



def getFFT(Y,Fs):
    L = len(Y)
    NFFT = 2**(math.ceil(math.log2(abs(L))))
    # NFFT = len(Y)
    Y = Y-np.mean(Y)
    Y_fft = fft(np.array(Y), NFFT)/NFFT
    Y_fft = 2*np.abs(Y_fft[0:int((NFFT/2))])
    f = Fs/2*np.linspace(0,1,int(NFFT/2))
    return Y_fft, f

def getFFT10K(Y,Fs):
    L = len(Y)
    NFFT = 2**(math.ceil(math.log2(abs(L))))
    # NFFT = len(Y)
    Y = Y-np.mean(Y)
    Y_fft = fft(np.array(Y), NFFT)/NFFT
    Y_fft = 2*np.abs(Y_fft[0:int((NFFT/2))])
    f = Fs/2*np.linspace(0,1,int(NFFT/2))

    # Trim FFT values beyond 10,000 Hz
    cutoff_frequency = 10000
    valid_indices = f <= cutoff_frequency
    Y_fft = Y_fft[valid_indices]
    f = f[valid_indices]

    return Y_fft, f


# def getFFT20K(Y,Fs):
#     L = len(Y)
#     NFFT = 2**(math.ceil(math.log2(abs(L))))
#     # NFFT = len(Y)
#     Y = Y-np.mean(Y)
#     Y_fft = fft(np.array(Y), NFFT)/NFFT
#     Y_fft = 2*np.abs(Y_fft[0:int((NFFT/2))])
#     f = Fs/2*np.linspace(0,1,int(NFFT/2))

#     # Trim FFT values except 20,000-40,000 Hz
#     valid_indices = ((f >= 20000) & (f <= 40000))
#     Y_fft = Y_fft[valid_indices]
#     f = f[valid_indices]

#     return Y_fft, f

def getFFT20K(Y,Fs, h, l):
    L = len(Y)
    NFFT = 2**(math.ceil(math.log2(abs(L))))
    # NFFT = len(Y)
    Y = Y-np.mean(Y)
    Y_fft = fft(np.array(Y), NFFT)/NFFT
    Y_fft = 2*np.abs(Y_fft[0:int((NFFT/2))])
    f = Fs/2*np.linspace(0,1,int(NFFT/2))

    # Trim FFT values except 20,000-40,000 Hz
    valid_indices = ((f >= h) & (f <= l))
    Y_fft = Y_fft[valid_indices]
    f = f[valid_indices]

    return Y_fft, f

 
# def getFFT(data,fs):
#     NFFT = len(data)
#     y=data-np.mean(data)
#     yf1 = fft(np.array(data), NFFT)/NFFT
#     Y = 2*abs(yf1[range(int(NFFT/2)+1)])
#     f = np.linspace(0, int(fs/2), int(NFFT/2))
#     return Y,f


    
def FFTAnalysisTwoSide(y,Fs):
    L=len(y)
    NFFT=L
    y=y-np.mean(y)
    Y=fft(np.array(y),NFFT)
    f=(Fs/2)*(np.linspace(-1,1,NFFT))
    return Y,f