import json
import numpy as np
import statistics
from scipy.fftpack import fft,ifft, hilbert
from scipy import signal
import datetime
import math
from app.SPFunctions.fftFunctions import getFFT, FFTAnalysisTwoSide
# from spectral_coherence_welch import Spectral_Coherence_Welch
import pdb


def omegaArithmetic(data, macID, fs=25600):
    vib_raw = data
    # print("from AVD")
    """Acc twf and spectrum"""
    # pdb.set_trace()
    accelerationTWF = np.array(vib_raw)
    accelerationSptrm, f_acc = getFFT(vib_raw, fs)
    twf = np.linspace(0, (len(data)-1)/fs, (len(data)))
    
    """Velocity twf and spectrum"""
    Y_complex, f_complex = FFTAnalysisTwoSide(accelerationTWF,fs)
    Y_complex_vel = (Y_complex*9.8*1000)/(2*np.pi*(fs/2 - abs(f_complex)))
    
    if macID == "70:B8:F6:02:49:34":
        for i in np.arange(len(Y_complex_vel)):
            if fs/2 - abs(f_complex[i]) <= 10:
                Y_complex_vel[i] = 0
    else:
        for i in np.arange(len(Y_complex_vel)):
            if fs/2 - abs(f_complex[i]) <= 10:
                Y_complex_vel[i] = 0


    Y_vel = ifft(Y_complex_vel, len(Y_complex_vel))
    magY_vel = np.real(Y_vel)
    velocityTWF = magY_vel - np.mean(magY_vel)
    velocitySptrm, f_vel = getFFT(velocityTWF, fs)
    
    """Displacement twf and spectrum"""
    Y_complex_dis = (Y_complex_vel*1000)/(2*np.pi*(fs/2 - abs(f_complex)))
    
    for i in np.arange(len(Y_complex_dis)):
        if fs/2 - abs(f_complex[i]) <= 10:
            Y_complex_dis[i] = 0
    Y_dis = ifft(Y_complex_dis, len(Y_complex_dis))
    magY_dis = np.real(Y_dis)
    displacementTWF = magY_dis - np.mean(magY_dis)
    displacementSptrm, f_dis = getFFT(displacementTWF, fs)
    
    
    return accelerationTWF.round(4), accelerationSptrm.round(4), velocityTWF.round(4), velocitySptrm.round(4), displacementTWF.round(4), \
        displacementSptrm.round(4), f_acc.round(4), f_vel.round(4), f_dis.round(4), twf.round(4)


def getRMS(datalist):
    ms = 0
    for data in datalist:
        ms+=data**2
    ms/=float(len(datalist))
    rms = (round(float(math.sqrt(ms)),2))
    return rms

def getPeak(datalist):
    max=0
    for i in datalist:
        if i > max:
            max = i
    return max

def getPeak_to_peak(datalist):
    max = 0
    min = 0
    for i in datalist:
        if i > max:
            max = i
        elif i < min:
            min = i
    return max-min

def peakDetect(Y_vel,f,f_desired):
    froi = np.nonzero(f_desired)[0]
    fft_intersted = np.array(Y_vel)[froi]
    freq_intersted = np.array(f)[froi]
    peak_value = max(fft_intersted)
    peak_index = list(fft_intersted).index(peak_value)
    f_peak = freq_intersted[peak_index]
    return peak_value, f_peak

def getEnvelope(data):
    dt = data - np.mean(data)
    ht = hilbert(data)
    analytical_signal = np.sqrt(dt**2+ht**2)
    amplitude_envelope = np.abs(analytical_signal)
    return amplitude_envelope.round(4)


def bandPassFilter(df, high, low, fs):
    sos = signal.cheby1(10, 1, high, 'hp', fs=fs, output='sos')
    filtered = signal.sosfilt(sos, df)
    sos2 = signal.cheby1(8, 1, low, 'lp', fs=fs, output='sos')
    filteredn = signal.sosfilt(sos2, filtered)
    return filteredn

def highPassFilter(df, high, fs):
    sos = signal.cheby1(10, 1, high, 'hp', fs=fs, output='sos')
    filtered = signal.sosfilt(sos, df)
    return filtered

def bandStopFilter(df, low, high, fs, attenuation=8):
    # Design a band-stop filter with Chebyshev Type II filter
    # Adjust attenuation to control output flatness
    sos = signal.cheby2(10, attenuation, [low, high], 'stop', fs=fs, output='sos')
    filtered = signal.sosfilt(sos, df)
    return filtered


def StatFunctionsAdjustment(originalValue, signalType, axis, statfun):

    if signalType == 'acceleration':
        if axis == 'x':
            if statfun == 'rms':
                value = originalValue - 0.01
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 0.075
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 0.17
                if value < 0:
                    value = 0
        elif axis == 'y':
            if statfun == 'rms':
                value = originalValue - 0.01
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 0.005
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 0.17
                if value < 0:
                    value = 0
        elif axis == 'z':
            if statfun == 'rms':
                value = originalValue - 0.01
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 0.08
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 0.22
                if value < 0:
                    value = 0

    if signalType == 'velocity':
        if axis == 'x':
            if statfun == 'rms':
                # value = originalValue - 0.18
                value = originalValue - 0
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 0.58
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 1.1
                if value < 0:
                    value = 0
        elif axis == 'y':
            if statfun == 'rms':
                # value = originalValue - 0.22
                value = originalValue - 0
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 0.9
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 1.95
                if value < 0:
                    value = 0
        elif axis == 'z':
            if statfun == 'rms':
                # value = originalValue - 0.22
                value = originalValue - 0
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 1
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 2
                if value < 0:
                    value = 0

    if signalType == 'displacement':
        if axis == 'x':
            if statfun == 'rms':
                value = originalValue - 1.4
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 4.4
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 10
                if value < 0:
                    value = 0
        elif axis == 'y':
            if statfun == 'rms':
                value = originalValue - 2.8
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 5.5
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 14
                if value < 0:
                    value = 0
        elif axis == 'z':
            if statfun == 'rms':
                value = originalValue - 2.2
                if value < 0:
                    value = 0
            elif statfun == 'peak':
                value = originalValue - 5.5
                if value < 0:
                    value = 0
            elif statfun == 'p2p':
                value = originalValue - 15
                if value < 0:
                    value = 0

    return round(value,2)



def getFilterValues(fs, axis):
    if 29000 > fs > 22900:
        if axis in ['x','y']:
            highPass = 500
            lowPass = 10000
        elif axis in ['z']:
            highPass = 500
            lowPass = 5100
    elif 14200 > fs > 11400:
        if axis in ['x','y']:
            highPass = 500
            lowPass = 6000
        elif axis in ['z']:
            highPass = 500
            lowPass = 5100
    elif 7100 > fs > 5700:
        highPass = 500
        lowPass = 3200
    elif 3550 > fs > 2800:
        highPass = 500
        lowPass = 1600
    else:
        highPass = 500
        lowPass = 6000
    return highPass, lowPass


def omegaArithmeticNew(data, signal_type, fs=25600):

    vib_raw = data
    """Acc twf and spectrum"""
    # pdb.set_trace()
    accelerationTWF = np.array(vib_raw)
    accelerationSptrm, f_acc = getFFT(vib_raw, fs)
    twf = np.linspace(0, (len(data)-1)/fs, (len(data)))

    if signal_type == 'acceleration':
        return accelerationTWF.round(4), accelerationSptrm.round(4), f_acc.round(4), twf.round(4)
    
    """Velocity twf and spectrum"""
    Y_complex, f_complex = FFTAnalysisTwoSide(accelerationTWF,fs)
    Y_complex_vel = (Y_complex*9.8*1000)/(2*np.pi*(fs/2 - abs(f_complex)))

    for i in np.arange(len(Y_complex_vel)):
        if fs/2 - abs(f_complex[i]) <= 10:
            Y_complex_vel[i] = 0


    Y_vel = ifft(Y_complex_vel, len(Y_complex_vel))
    magY_vel = np.real(Y_vel)
    velocityTWF = magY_vel - np.mean(magY_vel)
    velocitySptrm, f_vel = getFFT(velocityTWF, fs)

    if signal_type == 'velocity':
        return velocityTWF.round(4), velocitySptrm.round(4), f_vel.round(4), twf.round(4)
    
    """Displacement twf and spectrum"""
    Y_complex_dis = (Y_complex_vel*1000)/(2*np.pi*(fs/2 - abs(f_complex)))
    
    for i in np.arange(len(Y_complex_dis)):
        if fs/2 - abs(f_complex[i]) <= 10:
            Y_complex_dis[i] = 0
    Y_dis = ifft(Y_complex_dis, len(Y_complex_dis))
    magY_dis = np.real(Y_dis)
    displacementTWF = magY_dis - np.mean(magY_dis)
    displacementSptrm, f_dis = getFFT(displacementTWF, fs)
    
    if signal_type == 'displacement':
        return displacementTWF.round(4), displacementSptrm.round(4), f_dis.round(4), twf.round(4)



# def CycloStationary(signal, Fs):
        
#     L = len(signal)  # Signal length
#     Nw = np.array([128])    # Window length (Must be an array or list)
#     Nv = np.floor(2/3 * Nw).astype(np.int32)  # Block overlap
#     nfft = 2 * Nw[0]   # FFT length
#     da = 1/ L   # Cyclic frequency resolution
#     a1 = 1     # First cyclic frequency bin to scan (i.e. cyclic frequency a1*da)
#     a2 = 300    # last cyclic frequency bin to scan (i.e. cyclic frequency a2*da)

#     # Loop over cyclic frequencies  
#     C = np.zeros(shape = (nfft, a2-a1+1), dtype = "complex_")
#     S = np.zeros(shape = (nfft, a2-a1+1), dtype = "complex_")
#     for k in np.arange(a1, a2+1):
#         Coh_C, Coh_Syx, Coh_Sy, Coh_Sx, Coh_f, Coh_K, Coh_Var_Reduc, Coh_thresh = Spectral_Coherence_Welch(signal, signal, k/L, nfft, Nv, Nw, "sym", 0.01)
#         C[:, k-a1] = Coh_C
#         S[:, k-a1] = Coh_Syx

#     # Plot results
#     # Fs = fs   # Sampling frequency in Hz
#     alpha = Fs * np.arange(start = a1, stop = a2+1) * da
#     f = Fs * Coh_f[0:int(nfft/2)]









