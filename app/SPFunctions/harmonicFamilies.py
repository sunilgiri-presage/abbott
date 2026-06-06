# -*- coding: utf-8 -*-
"""
Created on Wed Jan 10 23:20:47 2024

@author: kamal
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from numpy import sqrt, sin, pi, sign
import pandas as pd
import warnings


def getHarmonicFamilies(ampl, freq):
    
    s = np.std(ampl)         # Calculate the standard deviation of the amplitudes
    peak_height = 2*s        # Minimum height to detect a peak in the graph
    rel_height = 0.5         # Relative height at which the width of the peak is measured (in percentage with respect to its prominence)
                            # 1 means measured from the base.
    prominencia = 0.005      # Prominence: Minimum gradient that must be descended from the top of a peak to ascend to another, whatever it may be, higher.
    dist =  5                # minimal distance of two consequtive peaks (in samples) 

    peaks, _ = find_peaks(ampl, height = peak_height, distance = dist, prominence=(prominencia,  None))
    # print("Number of peaks found:",len(peaks),", their indices are:", peaks) #how many peaks are detected


    def _peak_prominences(amplitudes, peaks, wlen):
        """
        Calcula la prominencia de cada pico de la señal.
        Parametros
        ----------
        amplitudes : list
            Una lista de valores con picos.
        peaks : list
            Indices de los picos en `amplitudes`.
        wlen : np.intp
            Longitud de la ventana en número de muestras (ver `peak_prominences`) que se aproxima por 
            exceso al impar más cercano. Si wlen es más pequeño que 2 se usa la señal `amplitudes` entera.

        Valores de salida
        -------
        prominences : ndarray
            Las prominencias calculadas para cada pico en `peaks`.
        left_bases, right_bases : ndarray
            Las bases de cada pico como indices de `amplitudes` a la izquierda y derecha de cada pico.

        Raises
        ------
        ValueError
            Si el valor de `peaks` es un indice inválido para `amplitudes`.

        Warns
        -----
        PeakPropertyWarning
            Si la prominencia calculada de algún pico es 0.
        """

        # show_warning = False
        prominences = np.empty(len(peaks), dtype=np.float64)
        left_bases = np.empty(len(peaks), dtype=np.intp)
        right_bases = np.empty(len(peaks), dtype=np.intp)

        for peak_nr in range(len(peaks)):
            peak = peaks[peak_nr]
            i_min = 0
            i_max = len(amplitudes) - 1
            if not i_min <= peak <= i_max:
                raise ValueError("peak {} is not a valid index for `amplitudes`".format(peak))

            if 2 <= wlen:
                # Adjust window around the evaluated peak (within bounds);
                # if wlen is even the resulting window length is is implicitly
                # rounded to next odd integer
                i_min = max(peak - wlen // 2, i_min)
                i_max = min(peak + wlen // 2, i_max)

            # Find the left base in interval [i_min, peak]
            i = left_bases[peak_nr] = peak
            left_min = amplitudes[peak]
            while i_min <= i and amplitudes[i] <= amplitudes[peak]:
                if amplitudes[i] < left_min:
                    left_min = amplitudes[i]
                    left_bases[peak_nr] = i
                i -= 1

            # Find the right base in interval [peak, i_max]
            i = right_bases[peak_nr] = peak
            right_min = amplitudes[peak]
            while i <= i_max and amplitudes[i] <= amplitudes[peak]:
                if amplitudes[i] < right_min:
                    right_min = amplitudes[i]
                    right_bases[peak_nr] = i
                i += 1

            prominences[peak_nr] = amplitudes[peak] - max(left_min, right_min)
            # if prominences[peak_nr] == 0:
            #     show_warning = True

        # if show_warning:
            # warnings.warn("some peaks have a prominence of 0", PeakPropertyWarning, stacklevel=2)

        return prominences, left_bases, right_bases

    def _peak_widths(x, peaks, rel_height, prominences, left_bases, right_bases):
        """
        Calcula la anchura de cada pico en la señal.
        Parametros
        ----------
        x : list
            Lista de valores con picos.
        peaks : list
            Indices de los picos en `x`.
        rel_height : np.float64
            Altura relativa a la cual se mide la altura del pico como
            porcentaje de su prominencia (ver `peak_widths`).
        prominences : ndarray
            Prominencias de cada pico en `peaks` tal y como fueron calculadas en `_peak_prominences`.
        left_bases, right_bases : ndarray
            Bases izquierdas y derechas de cada pico en `peaks` tal y como fueron calculadas en `_peak_prominences`.

        Salida
        -------
        widths : ndarray
            Anchuras de cada pico en número de muestras.
        width_heights : ndarray
            Altura de las líneas de contorno desde la cual se calcularon las anchuras `widths`.
            Esta altura es calculada como un porcentaje de la prominencia del pico.
        left_ips, right_ips : ndarray
            Posiciones interpoladas de los puntos de interesección izquierdo y derecho
            con la línea horizontal respectiva a la altura.

        Raises
        ------
        ValueError
            Si la `rel_height` es menor de 0.
            O si `peaks`, `left_bases` and `right_bases` no tienen las mismas dimensiones.
            O si los datos de `prominences` no cumplen la condición 
            ``0 <= left_base <= peak <= right_base < x.shape[0]`` para cada pico.

        Warnings
        --------
        PeakPropertyWarning
            Si la anchura calculada de algún pico es 0.
        """
        if rel_height < 0:
            raise ValueError('`rel_height` must be greater or equal to 0.0')
        if not (len(peaks) == prominences.shape[0] == left_bases.shape[0]
                == right_bases.shape[0]):
            raise ValueError("arrays in `prominence_data` must have the same shape as `peaks`")

        # show_warning = False
        widths = np.empty(len(peaks), dtype=np.float64)
        width_heights = np.empty(len(peaks), dtype=np.float64)
        left_ips = np.empty(len(peaks), dtype=np.float64)
        right_ips = np.empty(len(peaks), dtype=np.float64)


        for p in range(len(peaks)):
            i_min = left_bases[p]
            i_max = right_bases[p]
            peak = peaks[p]
            # Validate bounds and order
            # if not 0 <= i_min <= peak <= i_max < x.shape[0]:
                # with gil:
                    # raise ValueError("prominence data is invalid for peak {}".format(peak))
            height = width_heights[p] = x[peak] - prominences[p] * rel_height

            # Find intersection point on left side
            i = peak
            while i_min < i and height < x[i]:
                i -= 1
            left_ip = i
            if x[i] < height:
                # Interpolate if true intersection height is between samples
                left_ip += (height - x[i]) / (x[i + 1] - x[i])

            # Find intersection point on right side
            i = peak
            while i < i_max and height < x[i]:
                i += 1
            right_ip = i
            if  x[i] < height:
                # Interpolate if true intersection height is between samples
                right_ip -= (height - x[i]) / (x[i - 1] - x[i])

            widths[p] = right_ip - left_ip
            # if widths[p] == 0:
                # show_warning = True
            left_ips[p] = left_ip
            right_ips[p] = right_ip

        # if show_warning:
            # warnings.warn("some peaks have a width of 0", PeakPropertyWarning, stacklevel=2)

        return widths, width_heights, left_ips, right_ips



    ## calling the funtions _peak_prominences and _peak_widths
    prominences, left_bases, right_bases = _peak_prominences(ampl, peaks, 1)
    widths, width_heights, left_ips, right_ips = _peak_widths(ampl, peaks, rel_height, prominences, left_bases, right_bases)

    # Calculate the frequency values (Hz) of the left and right extremes of the uncertainties of each peak
    left_cotas = []
    right_cotas = []

    for p in range(len(peaks)):
        entera_l = int(left_ips[p])
        decimal_l = left_ips[p] - entera_l
        entera_r = int(right_ips[p])
        decimal_r = right_ips[p] - entera_r

        left_cotas.append((freq[entera_l+1]-freq[entera_l])*decimal_l + freq[entera_l])
        right_cotas.append((freq[entera_r+1]-freq[entera_r])*decimal_r + freq[entera_r])

    # Calculate the uncertainty values in terms of frequency values (Hz)
    widths_new = np.array(right_cotas) - np.array(left_cotas)
    widths = widths_new.copy()


    def peak_estimator(x, y, win="rect"):
        def corr_rect(deltaY):
            deltaF = 1 / (1 + deltaY)
            piDeltaF = pi*deltaF
            a = sin(piDeltaF)/piDeltaF
            return [deltaF, abs(a)]

        def corr_hann(deltaY):
            """Grandke estimator"""
            deltaF = (2 - deltaY) / (1 + deltaY)

            piDeltaF = pi*deltaF
            a = sin(piDeltaF)/piDeltaF
            b = 1/(1 - deltaF**2)
            return [deltaF, abs(a*b)]

        k0 = np.argmax(y)
        if k0 < 1 or k0 > len(y) - 2:
            raise ValueError("Index out of limits")

        # obtain neighbour points
        ns = (y[k0 - 1], y[k0 + 1])

        # line spacing (Hz)
        deltaF = x[2] - x[1]

        # var deltaY = ys[k0] / Math.max(prev, next);
        deltaY = y[k0] / max(ns[0], ns[1])

        if win == "rect":
            deltas = corr_rect(deltaY)
        elif win == "hann":
            deltas = corr_hann(deltaY)
        else:
            raise ValueError("Invalid window type")

        return [x[k0] + deltas[0]*deltaF*sign(ns[1] - ns[0]), y[k0]/deltas[1]]


    freq_new = freq.copy()
    ampl_new = ampl.copy()
    widths_new = widths.copy()


    """Finding harmonic families"""

    F = len(peaks)                          # F: number of components detected in the spectrum
    v = freq_new[peaks].copy()              # v: peak frequencies
    Dv = widths_new.copy()                  # Dv: uncertainties associated with each frequency peak
    A = ampl_new[peaks].copy()              # A: amplitudes associated with each frequency peak


    ### PARAMETERS TO MODIFY
    order_max = 10*F        # Maximum order with which a frequency of the series is calculated

    stop_crit = 5        # Maximum number of times that harmonic is not found, after which
                            # the algorithm stops iterating (stops searching for harmonics in the series)    


    ## Function to calculate the intervals for each harmonic r of a component i = [0:F-1]
    def harmonic_intervals(i):
        """
        Calculate the uncertainty intervals of each multiple r = 2,..., maximum_order, for a given spectral component i.
        Parameters
        ----------
        i: int
            Index of the component in the list of spectral components.

        Output values
        ----------
        intervals: list of lists
            Uncertainty intervals (expressed as a list, for example: [0.51, 0.85]) for each frequency multiple.
        """
        intervalos = []

        for r in range(2, order_max): 
            r_liminf = r * (v[i] - (Dv[i]/2))
            r_limsup = r * (v[i] + (Dv[i]/2))
            intervalos.append( [r_liminf, r_limsup] )

        return intervalos


    ## Calculate the intervals of each component i

    intervalo_componente = []

    for j in range(F): 
        j_liminf = v[j] - (Dv[j]/2)
        j_limsup = v[j] + (Dv[j]/2)
        intervalo_componente.append( [j_liminf, j_limsup] )



    ## Function to intersect intervals
    def intervals_intersection(intervals):
        '''
        Function that is used to find the intersection of several intervals.

        input arguments
        ----------
        intervals: a list of lists (intervals defined by their bottom and top dimensions)
        Example: intervals = [[10, 110],[20, 60],[25, 75]]

        Output values
        ----------
        [start, end] or [] (if the intersection is empty)
        '''
        start, end = intervals.pop() # extract the last element from the interval list

        while intervals:
            start_temp, end_temp = intervals.pop() # extracts the next last element from the interval list
            start = max(start, start_temp)         # compares the values with start and end with the ends of the last interval
            end = min(end, end_temp)
            if (start > end):                      # if the start value is greater than end, then the interval is empty
                return []
            elif (start <= end):
                return [start, end]


    ## Function to detect the next harmonic r of a component i
    def detect_harmonic(r,i):
        """
        Function that finds the harmonic of order r for the spectral component i.

        Input parameters
        ----------
        r: int
            Harmonic order. Value by which the fundamental frequency of component i is multiplied,
            thus finding the frequency of the harmonic that you want to search for in the spectrum.
        i: int
            Index to the list of spectral components.

        Output values
        ----------
        harmonic: float
            Frequency of the harmonic found. If no harmonic is found, the value of that harmonic is 0.
        index: int
            Index of the list of spectral components of the found harmonic.

        Raises
        ------
        ValueError
            If there are more than two uncertainty intervals of the spectral components that satisfy that
            Its intersection with the uncertainty interval of the harmonic of order r of component i is non-empty.
        """
        c = 0
        alista = []
        blista = []

        # update the uncertainty intervals for all harmonics of i for the new v[i] and Dv[i]
        rxvi = harmonic_intervals(i)

        for j, componente in enumerate(intervalo_componente):  # for each component

            # calculate the intersection of the uncertainty interval of component j with
            # the uncertainty interval of the rth harmonic of the i component (rxvi[r-2]). 
            z = intervals_intersection([componente, rxvi[r-2]])

            # If the interval is non-empty:
            if z:
                # count 1 non-empty intersection
                c += 1
                # add the ends of the intersection interval to the lists
                alista.append(z[0]) 
                blista.append(z[1])
                # give the value corresponding to the index found with non-empty intersection
                indice = j

                a, b = alista[0], blista[0]

        # If 2 intervals are found that satisfy that the intersection with rxvi[r-2] is not empty
        if c == 2:
            # calculate which of the two frequencies found is closer to r x frequency component i
            if abs(v[indice-1] - r*v[i]) < abs(v[indice] - r*v[i]):
                # update a, b and index accordingly
                a = alista[0]
                b = blista[0]
                indice -= 1
            else:
                a, b = alista[1], blista[1]
        # If there are more than 2 intervals that meet it: we show an error.
        elif c > 2:
            raise ValueError("There are more than 2 intervals that have non-empty intersection. This algorithm is designed for maximum 2 intervals.")
            # Possible improvements: develop this part of the function for more than 2 intervals with non-empty intersection.

        if not c: # If no harmonic has been found for that order r
            armonico = 0
            indice = None

        else: # If harmonic has been found
            armonico = v[indice]
            a = float(a)
            b = float(b)
            # update the v[i] and Dv[i]
            v[i] = (a+b) / (2*r)
            Dv[i] = (b-a) / r

        return armonico, indice


    ## Function to calculate the harmonic series of each component i=[0,F-1]
    def detect_harmonics_series(i):
        """
        Calculates the harmonic series of a given spectral component i

        Parameters
        ----------
        i: int
            Index of the component in the list of spectral components.

        Output values
        ----------
        harmonica_series: list
            List of harmonics found for component i. List positions that contain a 0 mean that no harmonic has been found for that order r
        harmonica_series_indices: list
            List of indices of the frequencies of the harmonic series found.
        number_harmonics: int
            Number of harmonics in the series without counting the fundamental frequency.
        """
        serie_armonica = [v[i]]
        serie_armonica_indices = [i]
        numero_armonicos = 1
        k = 0 # counter for stop criterio
        for r in range(2, order_max):

            # Find the harmonic number r
            armonico, indice = detect_harmonic(r,i)
            if (armonico == 0): # If you do not find harmonious
                k += 1 # update counter
            else: # If you find a harmonic
                numero_armonicos += 1
                k = 0
                serie_armonica_indices.append(indice)

            # If after k times no harmonic has been found, the series for
            if (k == stop_crit):
                serie_armonica = serie_armonica[0:r-k]
                break

            serie_armonica.append(armonico)
            serie_armonica[0] = v[i] # update the first value of the series since it has been modified

        return serie_armonica, serie_armonica_indices, numero_armonicos


    lista_series = []
    lista_numero_armonicos = []
    harmonic_freq = []
    harmonic_amp = []
    freq_indexes = []




    for i in range(F):
        series, indexes, no_har = detect_harmonics_series(i)
    #     print("indexesssssssss", indexes)

        if no_har > 1:
    #         print("\nOLD - The harmonic series found for the component", i, "is:", series, "and is made up of", no_har)
    #         print("\nNEW -The harmonic series found for the component", i, "is:", harm_freq, "and is made up of", no_har, "harmonics with the amplidue of", harm_ampl)


            lista_series.append(series)
            lista_numero_armonicos.append(no_har)



            # # introducing changes so that the detected frequencies and ampltiudes are directly in the data
            harm_freq = freq_new[np.array(peaks)[indexes]]
            harm_ampl = ampl_new[np.array(peaks)[indexes]]

            harmonic_freq.append(harm_freq)
            harmonic_amp.append(harm_ampl)
            freq_indexes.append([int(i) for i in peaks[indexes]])

            # print("peaks[indexes]peaks[indexes]peaks[indexes]peaks[indexes]", peaks[indexes])
            # freq_indexes.append([10, 20, 30])


    lista_D = [] 
    for i in range(F): # run for all detected components
        serie, indices, numero_armonicos = detect_harmonics_series(i) # get harmonic series
        if numero_armonicos > 1: # if there's more than 1 harmonic, caclulate D based on eq. 3
            rmax = len(serie) 
            H = 0
            for r in range(len(serie)):
                if (serie[r] != 0):
                    H = H + 1
            D = H/rmax
    #     else:
    #         D = 0.0

            lista_D.append(D)



    lista_R = []
    for i in range(F):
        serie, indices, numero_armonicos = detect_harmonics_series(i)
        if numero_armonicos > 1: # if there's more than 1 harmonic, calculate R based on eq. 7
            rmax = len(serie)
            Nmax = int(v[F-1]/serie[0])

            try:
                R = rmax/Nmax
            except ZeroDivisionError:
                R = 0.0   
    #     else: 
    #         R = 0.0

            lista_R.append(R)



    lista_THD = []
    for i in range(F):
        serie, indices, numero_armonicos = detect_harmonics_series(i)
        if numero_armonicos > 1:
            N = len(indices)
            THD = np.sqrt( sum(np.power(A[indices[1:N]], [2]*(N-1))) / (A[indices[0]]**2) )
    #     else:
    #         THD = 0.0

            lista_THD.append(THD)



    ## calculate a TOTAL SCORE for each series found
    puntuacion = [] # total score
    for j in range(len(harmonic_freq)):
        puntuacion.append( lista_D[j] + lista_R[j] + lista_THD[j] ) # weighted sum of scores of the previous criteria


    # collecting all the information in a data frame
    datos_series = {'Component': range(len(harmonic_freq)), 
                    # 'F_F (Hz)': (item[0] for item in lista_series),      # Algo found fundamental frequency
                    'org_F_F': (item[0] for item in harmonic_freq),      # Original fundamental frequency
                    # 'H_S': lista_series,                                 # Algo found Harmonic series
                    'org_H_S': harmonic_freq,                            # Original Harmonic series
                    'amp': harmonic_amp,                                 # Original amplitudes
                    'freq_index': freq_indexes,                                   # Index of fault frequency
                    'N': lista_numero_armonicos,                         # Number of harmonics in a family
                    'Total score': puntuacion,
                    'Criterion D': lista_D,
                    'Criterion R': lista_R,
                    'Criterion THD': lista_THD}
    df_series = pd.DataFrame(datos_series)


    top_20 = df_series.sort_values(by = 'Total score', ascending=False)[:120]

    final_result = {}
    for i, j in top_20.iterrows():
        final_result.update({
            round(j['org_F_F'], 3): 
            {
                'amp': list(map(lambda x: round(x,3), j['amp'])),
                'freq': list(map(lambda x: round(x,3), j['org_H_S'])),
                'index': list(map(lambda x: round(x,3), j['freq_index']))
            }
        })

    return final_result



























