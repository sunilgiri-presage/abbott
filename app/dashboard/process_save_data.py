from app.SPFunctions.SignalProcessing import getPeak, omegaArithmetic, getRMS, peakDetect, getEnvelope, getPeak_to_peak, bandPassFilter, StatFunctionsAdjustment, highPassFilter, getFilterValues, bandStopFilter
from app.SPFunctions.fftFunctions import getFFT, FFTAnalysisTwoSide
from app.SPFunctions.EHNR import EHNR
from app.SPFunctions.harmonicFamilies import getHarmonicFamilies
from app.SPFunctions.autoCorrelation import getAutoCorrelation
from app.thresholdFunctions.diagnostics import insert_missing_multiples, insert_zeros_amp
from app import models
from app import serializers
import numpy as np
from rest_framework.response import Response
from rest_framework import status
import json
# from scipy.stats import kurtosis
from app.bearingLib.pyvib.features import kurtosis
from django.forms.models import model_to_dict
import pdb
import datetime


def get_error_msg(message):
    try:
        errorData = json.loads(json.dumps(message))
        try:
            errorList = []
            count = 1
            for key in sorted(errorData.keys()):
                try:
                    errorList.append("{0}. {1} : {2} <br>".format(count, key.replace('_',' '), errorData[key][0]))
                except:
                    errorList.append("{0}. {1} : {2} <br>".format(count, key.replace('_',' '), errorData[key]))
                count += 1

            errorMsg = "".join(errorList)
            return errorMsg
        except:
            try:
                return str(errorData)
            except:
                return errorData
    except:
        return message

def saveData(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp):
    try:
        RawSerializer = serializers.RawDataMasterSerializer(data=data)
        if RawSerializer.is_valid():
            RawSerializer.save()
            macID = composite_key.split("_")[1]
            if axis in ['x','y']:
                # vibrationDataRawSignal = np.multiply(rData, 0.9)
                vibrationDataRawSignal = np.multiply(rData, 0.87)
            elif axis in ['z']:
                vibrationDataRawSignal = np.multiply(rData, 1.03)
            else:
                vibrationDataRawSignal = rData

            rpm_data = models.SignalProcessingMaster.objects.filter(composite_id=composite_key).values('rpm','high_pass','low_pass')
            try:
                RPM = float(rpm_data[0].get("rpm"))
            except:
                RPM = 0
            try:
                highPass = int(rpm_data[0].get("high_pass"))
            except:
                highPass = 10

            if axis == "z" and macID in ["E8:31:CD:38:7A:10"]:  #mach id of jinwoo korea
                lowPass = 5100
            else:
                try:
                    lowPass = int(rpm_data[0].get("low_pass"))
                except:
                    lowPass = 6000

            if macID in ["70:B8:F6:02:49:34"]:
                vibrationData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
            else:
                try:
                    vibrationDataUnFiltered = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
                    vibrationData = bandPassFilter(vibrationDataUnFiltered,highPass,lowPass,samplingFrequency)
                except:
                    vibrationData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)


            # vibrationData = vibrationDataRawSignal

            # vibrationData = vibrationDataUnFiltered
            # pdb.set_trace()
            if axis == 'x':
                if temp:
                    tempData = {"composite": composite_key, 'timestamp':local_dt, 'temp': round(temp,2),'asset_id': asset_id}
                    temp_serializer = serializers.TemperatureMasterSerializer(data=tempData)
                    if temp_serializer.is_valid():
                        temp_serializer.save()

            # if axis == 'x':
            #     vibrationData = vibrationData-0.03
            # elif axis in ['y','z']:
            #     vibrationData = vibrationData-0.04
            # else:
            #     vibrationData = vibrationData


            accelerationTWF, accelerationSptrm, velocityTWF, velocitySptrm, displacementTWF, displacementSptrm, f_acc, f_vel, f_dis, twf = omegaArithmetic(vibrationData, macID, int(samplingFrequency))
            velocity_twf_rms = getRMS(velocityTWF)
            velocity_sptrm_rms = getRMS(velocitySptrm)
            acc_twf = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(accelerationTWF),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
            acc_sptrm = {"high_pass": highPass, "low_pass": lowPass, "rpm": RPM, "timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(accelerationSptrm),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
            vel_twf = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"velocity_rms":velocity_twf_rms,"data":list(velocityTWF),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
            vel_sptrm = {"high_pass": highPass, "low_pass": lowPass, "rpm": RPM, "timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"velocity_rms":velocity_sptrm_rms,"data":list(velocitySptrm),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
            dis_twf = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(displacementTWF),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
            dis_sptrm = {"high_pass": highPass, "low_pass": lowPass, "rpm": RPM, "timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(displacementSptrm),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
            spectrum_x_axis_data = {"composite":composite_key,"asset_id":asset_id, "timestamp":local_dt ,"acceleration":f_acc,"velocity":f_vel,"displacement":f_dis}
            


            # ********************************** Acceleration Envelope Calculations **********************************

            try:
                try:
                    high_pass_value, low_pass_value = getFilterValues(int(samplingFrequency), axis)
                except:
                    high_pass_value = 500
                    low_pass_value = 6000
                envRawData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
                filteredEnvRawData = bandPassFilter(envRawData,high_pass_value, low_pass_value, int(samplingFrequency))
                accTwfEnvelope = getEnvelope(filteredEnvRawData)
                accSptrmEnvelope, _ = getFFT(accTwfEnvelope, samplingFrequency)
            except:
                accTwfEnvelope = []
                accSptrmEnvelope = []

            accTwfEnvelope_data = {"composite":composite_key, 'timestamp':local_dt, 'fs':samplingFrequency,"no_of_samples": no_of_samples,\
                                'data':accTwfEnvelope,'axis':axisOrientation,'asset_id':asset_id}
            accSptrmEnvelope_data = {"composite":composite_key, 'timestamp':local_dt, 'fs':samplingFrequency,"no_of_samples": no_of_samples,\
                                'data':accSptrmEnvelope,'axis':axisOrientation,'asset_id':asset_id}
            


            # ********************************** Auto Correlation Calculations **********************************
            
            # try:
            #     autoCorr = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
            #     filteredAutoCorr = bandPassFilter(autoCorr,500, 6000, int(samplingFrequency))
            #     envelopeAutoCorr = getEnvelope(filteredAutoCorr)
            #     auto_corr = getAutoCorrelation(envelopeAutoCorr)
            # except:
            #     auto_corr = []
            
            # autoCorrData = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":auto_corr,"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}


            # ********************************** Phase value calculations (common for all) **********************************
            # RPM = 2000

            try:
                # pdb.set_trace()
                peakValue = max(dis_twf.get("data"))
                peakValueIndex = list(dis_twf.get("data")).index(peakValue)
                if int(twf[peakValueIndex]/(60/RPM)*360) > 90:
                    phase = round(360+(90-(twf[peakValueIndex]/((60/RPM)*360))),2)
                else:
                    phase = round(90-(twf[peakValueIndex]/((60/RPM)*360)),2)

            except:
                phase = 0

            # ********************************** Acceleration Harmonics **********************************
            try:
                # pdb.set_trace()
                if RPM > 0:
                    f_rpm = RPM/60  # using for IMF data only, need to make dynamic from database (config app)
                    row = len(accelerationSptrm)*2
                    accelerationPeaks = []
                    accelerationPeakFrequency = []
                    for index in np.arange(5):
                        if index in [1,2]:
                            f_desired = (f_acc>=(f_rpm*(index+1)-2*(samplingFrequency/row))) & (f_acc<=(f_rpm*(index+1)+2*(samplingFrequency/row)))
                        elif index in [3,4]:
                            f_desired = (f_acc>=(f_rpm*(index+1)-3*(samplingFrequency/row))) & (f_acc<=(f_rpm*(index+1)+3*(samplingFrequency/row)))
                        else:
                            f_desired = (f_acc>=(f_rpm*(index+1)-(samplingFrequency/row))) & (f_acc<=(f_rpm*(index+1)+(samplingFrequency/row)))
                        vel_peak, vel_peak_axis = peakDetect(accelerationSptrm,f_acc,f_desired)
                        accelerationPeaks.append(round(vel_peak,3))
                        peak_value_index = np.where(f_acc == vel_peak_axis)
                        accelerationPeakFrequency.append(peak_value_index[0][0])

                    acceleration_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
                    'phase':phase,'one_amp':accelerationPeaks[0],'one_freq':accelerationPeakFrequency[0],\
                    'two_amp':accelerationPeaks[1],'two_freq':accelerationPeakFrequency[1],'three_amp':accelerationPeaks[2],\
                    'three_freq':accelerationPeakFrequency[2],'four_amp':accelerationPeaks[3],'four_freq':accelerationPeakFrequency[3],\
                    'five_amp':accelerationPeaks[4],'five_freq':accelerationPeakFrequency[4], 'asset_id':asset_id}
                else:
                    acceleration_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
                                'phase':phase,'one_amp':0,'one_freq':0,'two_amp':0,'two_freq':0,'three_amp':0,\
                                'three_freq':0,'four_amp':0,'four_freq':0,'five_amp':0,'five_freq':0,'asset_id':asset_id}
            except:
                acceleration_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
                                'phase':phase,'one_amp':0,'one_freq':0,'two_amp':0,'two_freq':0,'three_amp':0,\
                                'three_freq':0,'four_amp':0,'four_freq':0,'five_amp':0,'five_freq':0,'asset_id':asset_id}

            # ********************************** Velocity Harmonics **********************************

            try:
                if RPM > 0:
                    f_rpm = RPM/60 
                    row = len(velocitySptrm)*2
                    velocityPeaks = []
                    velocityPeakFrequency = []
                    index = 0.5
                    while index <= 5:
                    # for index in np.arange(5):
                        if index in [0.5, 1, 1.5, 2, 2.5]:
                            f_desired = (f_vel>=(f_rpm*(index)-2*(samplingFrequency/row))) & (f_vel<=(f_rpm*(index)+2*(samplingFrequency/row)))
                        elif index in [3, 3.5, 4, 4.5, 5]:
                            f_desired = (f_vel>=(f_rpm*(index)-3*(samplingFrequency/row))) & (f_vel<=(f_rpm*(index)+3*(samplingFrequency/row)))
                        else:
                            f_desired = (f_vel>=(f_rpm*(index)-(samplingFrequency/row))) & (f_vel<=(f_rpm*(index)+(samplingFrequency/row)))
                        vel_peak, vel_peak_axis = peakDetect(velocitySptrm,f_vel,f_desired)
                        velocityPeaks.append(round(vel_peak,3))
                        peak_value_index = np.where(f_vel == vel_peak_axis)
                        velocityPeakFrequency.append(peak_value_index[0][0])
                        index += 0.5

                    velocity_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
                                        'phase':phase,'half_amp': velocityPeaks[0],'half_freq': velocityPeakFrequency[0],'one_amp':velocityPeaks[1],'one_freq':velocityPeakFrequency[1],\
                                        'one_half_amp': velocityPeaks[2],'one_half_freq': velocityPeakFrequency[2],'two_amp':velocityPeaks[3],'two_freq':velocityPeakFrequency[3],\
                                            'two_half_amp': velocityPeaks[4],'two_half_freq': velocityPeakFrequency[4],'three_amp':velocityPeaks[5],'three_freq':velocityPeakFrequency[5],\
                                                'three_half_amp': velocityPeaks[6],'three_half_freq': velocityPeakFrequency[6],'four_amp':velocityPeaks[7],'four_freq':velocityPeakFrequency[7],\
                                                    'four_half_amp': velocityPeaks[8],'four_half_freq': velocityPeakFrequency[8],'five_amp':velocityPeaks[9],'five_freq':velocityPeakFrequency[9],\
                                                        'asset_id':asset_id}
                else:
                    velocity_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
                                'phase':phase,'half_amp': 0,'half_freq': 0,'one_amp':0,'one_freq':0,'one_half_amp': 0,'one_half_freq': 0,\
                                    'two_amp':0,'two_freq':0,'two_half_amp': 0,'two_half_freq': 0,'three_amp':0,'three_freq':0,\
                                        'three_half_amp': 0,'three_half_freq': 0,'four_amp':0,'four_freq':0,'four_half_amp': 0,'four_half_freq': 0,\
                                            'five_amp':0,'five_freq':0,'asset_id':asset_id}
                    
            except Exception as e:
                print("Some exception in velocity harmonics", e)
                velocity_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
                                'phase':phase,'half_amp': 0,'half_freq': 0,'one_amp':0,'one_freq':0,'one_half_amp': 0,'one_half_freq': 0,\
                                    'two_amp':0,'two_freq':0,'two_half_amp': 0,'two_half_freq': 0,'three_amp':0,'three_freq':0,\
                                        'three_half_amp': 0,'three_half_freq': 0,'four_amp':0,'four_freq':0,'four_half_amp': 0,'four_half_freq': 0,\
                                            'five_amp':0,'five_freq':0,'asset_id':asset_id}


            # ********************************** Velocity Harmonics for diagnostics **********************************
           
            # try:
            #     # pdb.set_trace()
            #     final_result = getHarmonicFamilies(velocitySptrm, f_vel)
            #     velocity_auto_harmonics_data = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation, "data": final_result, "asset_id": asset_id}
            #     if RPM > 0:
            #         fundamental_frequency = round(RPM/60, 3)
            #         max_difference = 1.7
            #         # closest keys to find frequency near fundamental frequency for 1X
            #         closest_keys = [key for key in final_result.keys() if abs(key - fundamental_frequency) <= max_difference]
            #         if len(closest_keys) > 0:
            #             closest_key = min(closest_keys)
            #             closest_values = final_result[closest_key]
                       
            #             found_frequencies, zero_indices = insert_missing_multiples(closest_values.get("freq"), 5)     # completing harmonic series upto 10x and inserting 0 where frequency missing
            #             updated_amplitudes = insert_zeros_amp(closest_values.get("amp"), zero_indices)                # inserting zero to amplitude list where frequency is missing
            #             updated_indices = insert_zeros_amp(closest_values.get("index"), zero_indices)                 # inserting zero to indexes list where frequency is missing
            #             # one_amp = closest_values.get("amp")[0], 
            #             diagnostics_value_data = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation, "asset_id": asset_id,\
            #                                         "one_amp": updated_amplitudes[0], "two_amp": updated_amplitudes[1], "three_amp": updated_amplitudes[2], \
            #                                             "four_amp": updated_amplitudes[3], "five_amp": updated_amplitudes[4], "six_amp": updated_amplitudes[5], \
            #                                                 "seven_amp": updated_amplitudes[6], "eight_amp": updated_amplitudes[7], "nine_amp": updated_amplitudes[8], \
            #                                                     "ten_amp": updated_amplitudes[9], "signal_type": "velocity", \
            #                                                         "four_to_seven_amp": updated_amplitudes[4]+updated_amplitudes[5]+updated_amplitudes[6]+updated_amplitudes[7]}
            #             diagnostics_value_data_serializer = serializers.DiagnosticsValuesMasterSerializer(data=diagnostics_value_data)
            #             if diagnostics_value_data_serializer.is_valid():
            #                 diagnostics_value_data_serializer.save()
            #             else:
            #                 pass
            #     else:
            #         pass
            # except:
            #     velocity_auto_harmonics_data = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation, "data": final_result, "asset_id": asset_id}

            # ********************************** Displacement Harmonics **********************************
            # try:
            #     f_rpm = RPM/60  # using for IMF data only, need to make dynamic from database (config app)
            #     row = len(displacementSptrm)
            #     displacementPeaks = []
            #     displacementPeakFrequency = []
            #     for index in np.arange(10):
            #         f_desired = (f_vel>=(f_rpm*(index+1)-(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+(samplingFrequency/row)))
            #         vel_peak, vel_peak_axis = peakDetect(displacementSptrm,f_vel,f_desired)
            #         displacementPeaks.append(round(vel_peak,3))
            #         peak_value_index = np.where(f_vel == vel_peak_axis)
            #         displacementPeakFrequency.append(peak_value_index[0][0])
            # except:
            #     pass

            # displacement_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
            #                     'phase':phase,'one_amp':displacementPeaks[0],'one_freq':displacementPeakFrequency[0],\
            #                     'two_amp':displacementPeaks[1],'two_freq':displacementPeakFrequency[1],'three_amp':displacementPeaks[2],\
            #                     'three_freq':displacementPeakFrequency[2],'four_amp':displacementPeaks[3],'four_freq':displacementPeakFrequency[3],\
            #                     'five_amp':displacementPeaks[4],'five_freq':displacementPeakFrequency[4],'six_amp':displacementPeaks[5],\
            #                     'six_freq':displacementPeakFrequency[5],'seven_amp':displacementPeaks[6],'seven_freq':displacementPeakFrequency[6],\
            #                     'eight_amp':displacementPeaks[7],'eight_freq':displacementPeakFrequency[7],'nine_amp':displacementPeaks[8],\
            #                     'nine_freq':displacementPeakFrequency[8],'ten_amp':displacementPeaks[9],'ten_freq':displacementPeakFrequency[9],\
            #                     'asset_id':asset_id}



            
            # ********************************** Acceleration Envelope (both time & freq) **********************************
            # ********************************** High pass filter for envelope only for nbc data set **********************************
            # if macID == 'wl_22':
            #     try:
            #         vibrationDataRaw - np.mean(vibrationDataRaw)
            #         accelerationTWF_filtered = bandPassFilter(vibrationDataRaw,1000,2000,samplingFrequency)
            #         accTwfEnvelope = getEnvelope(accelerationTWF_filtered)
            #         accSptrmEnvelope, _ = getFFT(accTwfEnvelope, samplingFrequency)
            #     except:
            #         accTwfEnvelope = []
            #         accSptrmEnvelope = []
            # else:
            


            # ********************************** acceleration statistical parameters **********************************
            try:
                acceleration_time_rms_org = getRMS(accelerationTWF)
                # acceleration_time_rms = round(acceleration_time_rms_org, 2)

                if macID in ["70:B8:F6:02:49:34"]:
                    acceleration_time_rms = round(acceleration_time_rms_org, 2)
                else:
                    acceleration_time_rms = StatFunctionsAdjustment(acceleration_time_rms_org, 'acceleration', axis, 'rms')

                acceleration_time_peak = getPeak(accelerationTWF)
                acceleration_time_peak_to_peak = getPeak_to_peak(accelerationTWF)
                # acceleration_time_peak = acceleration_time_rms * 1.414
                # acceleration_time_peak_to_peak = acceleration_time_peak * 2
            except:
                acceleration_time_rms = 0
                acceleration_time_peak = 0
                acceleration_time_peak_to_peak = 0


            try:
                acceleration_time_kurtosis = kurtosis(np.array(accelerationTWF))
            except:
                acceleration_time_kurtosis = 0

            dataAccelerationStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(acceleration_time_kurtosis,2),"rms":acceleration_time_rms,"axis":axisOrientation,\
                                    "composite":composite_key,"asset_id":asset_id,"peak":round(acceleration_time_peak,2),"peak_to_peak":round(acceleration_time_peak_to_peak,2)}

            # ********************************** velocity statistical parameters **********************************
            try:
                # pdb.set_trace()
                velocity_time_rms_org = getRMS(velocityTWF)
                # velocity_time_rms = round(velocity_time_rms_org, 2)

                if macID in ["70:B8:F6:02:49:34"]:
                    velocity_time_rms = round(velocity_time_rms_org, 2)
                else:
                    velocity_time_rms = StatFunctionsAdjustment(velocity_time_rms_org, 'velocity', axis, 'rms')

                velocity_time_peak = getPeak(velocityTWF)
                velocity_time_peak_to_peak = getPeak_to_peak(velocityTWF)
                # velocity_time_peak = velocity_time_rms * 1.414
                # velocity_time_peak_to_peak = velocity_time_peak * 2

            except:
                velocity_time_rms = 0
                velocity_time_peak = 0
                velocity_time_peak_to_peak = 0


            try:
                velocity_time_kurtosis = kurtosis(np.array(velocityTWF))
            except:
                velocity_time_kurtosis = 0

            dataVelocityStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(velocity_time_kurtosis,2),"rms":velocity_time_rms,"axis":axisOrientation,\
                                        "composite":composite_key,"asset_id":asset_id,"peak":round(velocity_time_peak,2),"peak_to_peak":round(velocity_time_peak_to_peak,2)}


            # ********************************** displacement statistical parameters **********************************
            try:
                displacement_time_rms_org = getRMS(displacementTWF)
                # displacement_time_rms = round(displacement_time_rms_org, 2)

                if macID in ["70:B8:F6:02:49:34"]:
                    displacement_time_rms = round(displacement_time_rms_org, 2)
                else:
                    displacement_time_rms = StatFunctionsAdjustment(displacement_time_rms_org, 'displacement', axis, 'rms')

                displacement_time_peak = getPeak(displacementTWF)
                displacement_time_peak_to_peak = getPeak_to_peak(displacementTWF)
                # displacement_time_peak = displacement_time_rms * 1.414
                # displacement_time_peak_to_peak = displacement_time_peak * 2
            except:
                displacement_time_rms = 0
                displacement_time_peak = 0
                displacement_time_peak_to_peak = 0


            try:
                displacement_time_kurtosis = kurtosis(np.array(displacementTWF))
            except:
                displacement_time_kurtosis = 0

            dataDisplacementStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(displacement_time_kurtosis,2),"rms":displacement_time_rms,"axis":axisOrientation,\
                                        "composite":composite_key,"asset_id":asset_id,"peak":round(displacement_time_peak,2),"peak_to_peak":round(displacement_time_peak_to_peak,2)}



            # ********************************** EHNR Calculations **********************************
            try:
                ehnr = EHNR(np.array(vibrationData), samplingFrequency)
                ehnrData = {"composite": composite_key,"timestamp": local_dt,"ehnr": round(ehnr, 2),"axis": axisOrientation,"asset_id": asset_id}
            except:
                ehnrData = {"composite": composite_key,"timestamp": local_dt,"ehnr": 0,"axis": axisOrientation,"asset_id": asset_id}



            # ********************************** Bearing Fault Frequencies **********************************

            try:
                bearingInstance = models.BearingDetailMaster.objects.get(mount_id=mount_id)
                bearingData = model_to_dict(bearingInstance)
            except:
                bearingData = {"bpfo": None,"bpfi": None,"bsf": None,"ftf": None}

            # ********************************** Acceleration Spectrum Bearing Fault Frequencies **********************************
            bff_data_acc = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation,  "signal_type": "Acceleration",  "asset_id":asset_id }
            for falutFrequency in ['bpfo','bpfi','bsf','ftf']:
                if bearingData.get(falutFrequency):
                    if falutFrequency == 'bsf':
                        BFF = float(bearingData.get(falutFrequency)) * (RPM/60) *2
                    else:
                        BFF = float(bearingData.get(falutFrequency)) * (RPM/60)
                    f_acc = np.array(f_acc)
                    peaks_acc = []
                    peak_frequence_acc = []
                    row_acc = len(accelerationSptrm)*2

                    for index in range(1,6,1):
                        try:
                            f_desired = (f_acc>=(BFF*(index)-(samplingFrequency/row_acc))) & (f_acc<=(BFF*(index)+(samplingFrequency/row_acc)))
                            acc_peak, acc_peak_axis = peakDetect(accelerationSptrm,f_acc,f_desired)
                            peaks_acc.append(round(float(acc_peak),3))
                            peak_value_index = np.where(f_acc == acc_peak_axis)
                            peak_frequence_acc.append(peak_value_index[0][0])
                            bff_data_acc.update({falutFrequency+"_amp": peaks_acc, falutFrequency+"_freq": peak_frequence_acc})
                        except Exception as e:
                            print("exception in acc bff",composite_key , e)
                            pass
                else:
                    bff_data_acc.update({falutFrequency+"_amp": [], falutFrequency+"_freq": []})

            # ********************************** Velocity Spectrum Bearing Fault Frequencies **********************************
            bff_data_vel = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation,  "signal_type": "Velocity",  "asset_id":asset_id }
            for falutFrequency in ['bpfo','bpfi','bsf','ftf']:
                if bearingData.get(falutFrequency):
                    # BFF = float(bearingData.get(falutFrequency)) * (RPM/60)
                    if falutFrequency == 'bsf':
                        BFF = float(bearingData.get(falutFrequency)) * (RPM/60) *2
                    else:
                        BFF = float(bearingData.get(falutFrequency)) * (RPM/60)
                    f_vel = np.array(f_vel)
                    peak_vel = []
                    peak_frequency_vel = []
                    row_vel = len(velocitySptrm)*2

                    for index in range(1,6,1):
                        try:
                            f_desired = (f_vel>=(BFF*(index)-(samplingFrequency/row_vel))) & (f_vel<=(BFF*(index)+(samplingFrequency/row_vel)))
                            vel_peak, vel_peak_axis = peakDetect(velocitySptrm,f_vel,f_desired)
                            peak_vel.append(round(float(vel_peak),3))
                            peak_value_index = np.where(f_vel == vel_peak_axis)
                            peak_frequency_vel.append(peak_value_index[0][0])
                            bff_data_vel.update({falutFrequency+"_amp": peak_vel, falutFrequency+"_freq": peak_frequency_vel})
                        except:
                            pass
                else:
                    bff_data_vel.update({falutFrequency+"_amp": [], falutFrequency+"_freq": []})
            
            finalDataBFF = [bff_data_acc, bff_data_vel]
            




            accTWFSerializer = serializers.AccelerationTWFMasterSerializer(data=acc_twf)
            if accTWFSerializer.is_valid():
                accSptrmSerializer = serializers.AccelerationSpectrumMasterSerializer(data=acc_sptrm)
                if accSptrmSerializer.is_valid():
                    velocityTWFSerializer = serializers.VelocityTWFMasterSerializer(data=vel_twf)
                    if velocityTWFSerializer.is_valid():
                        velocitySptrmSerializer = serializers.VelocitySpectrumMasterSerializer(data=vel_sptrm)
                        if velocitySptrmSerializer.is_valid():
                            displacementTWFSerializer = serializers.DisplacementTWFMasterSerializer(data=dis_twf)
                            if displacementTWFSerializer.is_valid():
                                displacementSptrmSerializer = serializers.DisplacementSpectrumMasterSerializer(data=dis_sptrm)
                                if displacementSptrmSerializer.is_valid():
                                    acceleration_harmonics_serializer = serializers.AccelerationHarmonicsMasterSerializer(data=acceleration_harmonics_data)
                                    if acceleration_harmonics_serializer.is_valid():
                                        velocity_harmonics_serializer = serializers.VelocityHarmonicsMasterSerializer(data=velocity_harmonics_data)
                                        if velocity_harmonics_serializer.is_valid():
                                            # velocity_auto_harmonics_data_serializer = serializers.AutoVelocityHarmonicsMasterSerializer(data=velocity_auto_harmonics_data)
                                            # if velocity_auto_harmonics_data_serializer.is_valid():
                                                spectrum_data_serializer = serializers.SpectrumChartDataMasterSerializer(data=spectrum_x_axis_data)
                                                if spectrum_data_serializer.is_valid():
                                                    # health_serializer = serializers.DeviceHealthStatusSerializer(data=device_health_data)
                                                    # if health_serializer.is_valid():
                                                        accTwfEnvelope_serializer = serializers.EnvelopeTWFMasterSerializer(data=accTwfEnvelope_data)
                                                        if accTwfEnvelope_serializer.is_valid():
                                                            accSptrmEnvelope_serializer = serializers.EnvelopeSpectrumMasterSerializer(data=accSptrmEnvelope_data)
                                                            if accSptrmEnvelope_serializer.is_valid():
                                                                acceleration_stat_time_serializer = serializers.AccelerationStatTimeMasterSerializer(data=dataAccelerationStatTimeMaster)
                                                                if acceleration_stat_time_serializer.is_valid():
                                                                    # auto_correlation_serializer = serializers.AutoCorrelationMasterSerializer(data=autoCorrData)
                                                                    # if auto_correlation_serializer.is_valid():
                                                                        velocity_stat_time_serializer = serializers.VelocityStatTimeMasterSerializer(data=dataVelocityStatTimeMaster)
                                                                        if velocity_stat_time_serializer.is_valid():
                                                                            # velocity_stat_freq_serializer = serializers.VelocityStatFreqMasterSerializer(data=dataVelocityStatFreqMaster)
                                                                            # if velocity_stat_freq_serializer.is_valid():
                                                                                displacement_stat_time_serializer = serializers.DisplacementStatTimeMasterSerializer(data=dataDisplacementStatTimeMaster)
                                                                                if displacement_stat_time_serializer.is_valid():
                                                                                    # displacement_stat_freq_serializer = serializers.DisplacementStatFreqMasterSerializer(data=dataDisplacementStatFreqMaster)
                                                                                    # if displacement_stat_freq_serializer.is_valid():
                                                                                    bff_serializer = serializers.BearingFaultFrequenciesMasterSerializer(data = finalDataBFF, many=True)
                                                                                    if bff_serializer.is_valid():
                                                                                        ehnr_serializer = serializers.FrequencyDomainFeatuersSerializer(data = ehnrData)
                                                                                        if ehnr_serializer.is_valid():
                                                                                            accTWFSerializer.save()
                                                                                            accSptrmSerializer.save()
                                                                                            velocityTWFSerializer.save()
                                                                                            velocitySptrmSerializer.save()
                                                                                            displacementTWFSerializer.save()
                                                                                            displacementSptrmSerializer.save()
                                                                                            acceleration_harmonics_serializer.save()
                                                                                            velocity_harmonics_serializer.save()
                                                                                            # velocity_auto_harmonics_data_serializer.save()
                                                                                            spectrum_data_serializer.save()
                                                                                            # health_serializer.save()
                                                                                            accTwfEnvelope_serializer.save()
                                                                                            accSptrmEnvelope_serializer.save()
                                                                                            acceleration_stat_time_serializer.save()
                                                                                            # auto_correlation_serializer.save()
                                                                                            velocity_stat_time_serializer.save()
                                                                                            # velocity_stat_freq_serializer.save()
                                                                                            displacement_stat_time_serializer.save()
                                                                                            # displacement_stat_freq_serializer.save()
                                                                                            bff_serializer.save()
                                                                                            ehnr_serializer.save()
                                                                                            return "All Data Saved", status.HTTP_201_CREATED
                                                                                        return get_error_msg(ehnr_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                                                    return get_error_msg(bff_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                                                    # return get_error_msg(displacement_stat_freq_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                                                return get_error_msg(displacement_stat_time_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                                            # return get_error_msg(velocity_stat_freq_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                                        return get_error_msg(velocity_stat_time_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                                    # return get_error_msg(auto_correlation_serializer), status.HTTP_400_BAD_REQUEST
                                                                return get_error_msg(acceleration_stat_time_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                            return get_error_msg(accSptrmEnvelope_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                        return get_error_msg(accTwfEnvelope_serializer.errors), status.HTTP_400_BAD_REQUEST                                
                                                    # return get_error_msg(health_serializer.errors), status.HTTP_400_BAD_REQUEST
                                                return get_error_msg(spectrum_data_serializer.errors), status.HTTP_400_BAD_REQUEST
                                            # return get_error_msg(velocity_auto_harmonics_data_serializer.errors), status.HTTP_400_BAD_REQUEST
                                        return get_error_msg(velocity_harmonics_serializer.errors), status.HTTP_400_BAD_REQUEST
                                    return get_error_msg(acceleration_harmonics_serializer.errors), status.HTTP_400_BAD_REQUEST
                                return get_error_msg(displacementSptrmSerializer.errors), status.HTTP_400_BAD_REQUEST
                            return get_error_msg(displacementTWFSerializer.errors), status.HTTP_400_BAD_REQUEST
                        return get_error_msg(velocitySptrmSerializer.errors), status.HTTP_400_BAD_REQUEST
                    return get_error_msg(velocityTWFSerializer.errors), status.HTTP_400_BAD_REQUEST
                return get_error_msg(accSptrmSerializer.errors), status.HTTP_400_BAD_REQUEST
            return get_error_msg(accTWFSerializer.errors), status.HTTP_400_BAD_REQUEST
            # except:
            #     return "Only Raw Data saved", status.HTTP_400_BAD_REQUEST
        else:
            return get_error_msg(RawSerializer.errors), status.HTTP_400_BAD_REQUEST
    except:
        return "Something went wrong.", status.HTTP_400_BAD_REQUEST


def saveDataAcoustic(data, acousticData, fs):
    excitation_voltage = 3.3
    n = 12
    high = 10000
    low = 40000

    RawSerializer = serializers.RawDataMasterSerializer(data=data)
    if RawSerializer.is_valid():
        RawSerializer.save()
    else:
        return get_error_msg(RawSerializer.errors), status.HTTP_400_BAD_REQUEST

    try:
        df = np.array(acousticData[20:])

        df_processed = df * excitation_voltage / (2 ** n - 1)
        df_processed = df_processed - np.mean(df_processed)

        # show in trend
        processed_rms = getRMS(df_processed)
        rms_db_raw = 20 * np.log10(processed_rms/ 2048)
        rms_db = 132 - np.abs(rms_db_raw)


        # show in trend
        df_filtered = bandPassFilter(df_processed, high, low, fs)  # save df_filtered for twf data on dashboard
        processed_rms_filtered = getRMS(df_filtered)
        rms_dB_filtered_raw = 20 * np.log10(processed_rms_filtered/ 2048)
        rms_dB_filtered = 132 - np.abs(rms_dB_filtered_raw)

        try:
            acousticRMSData = {"composite": data.get("composite"), 'timestamp':data.get("timestamp"), \
                               'acoustic_db': round(rms_dB_filtered_raw,2), 'acoustic_rms': round(rms_db,2), \
                                'asset_id': data.get("asset_id"), 'flag': True}   # saving flag == True only of complete spectrum data (ble in this case not wired)
            acoustic_serializer = serializers.AcousticsMasterSerializer(data=acousticRMSData)
            if acoustic_serializer.is_valid():
                acoustic_serializer.save()
            else:
                return "Something went wrong while saving rms data {0}".format(get_error_msg(acoustic_serializer.errors)), status.HTTP_404_NOT_FOUND
        except Exception as e:
            return "Something went wrong while saving rms data {0}".format(e), status.HTTP_404_NOT_FOUND


        try:
            high_stop_1 = 17000
            low_stop_1 = 19100
            df_filtered_cleared_1 = bandStopFilter(df_processed, high_stop_1, low_stop_1, fs)

            high_stop_2 = 29900
            low_stop_2 = 31600
            df_filtered_cleared_2 = bandStopFilter(df_filtered_cleared_1, high_stop_2, low_stop_2, fs, attenuation=13)  # save df_filtered for spectrum data on dashboard
        except Exception as e:
            return "Something went wrong in filter of acoustic data {0}".format(e), status.HTTP_404_NOT_FOUND

        # try:
        #     df_fft, f = getFFT(df_filtered_cleared_2, fs)

        #     acousticSpectrumData = {"composite": data.get("composite"), 'timestamp':data.get("timestamp"), \
        #                             'twf_data': np.round(df_filtered, 3), 'spectrum_data': np.round(df_fft, 3), 'frequency_data': np.round(f, 3), \
        #                                 'asset_id': data.get("asset_id"),'axis': data.get("axis")}
        #     acoustic_spectrum_serializer = serializers.AcousticsSpectrumMasterSerializer(data=acousticSpectrumData)
        #     if acoustic_spectrum_serializer.is_valid():
        #         acoustic_spectrum_serializer.save()
        #     else:
        #         return "Something went wrong while saving acoustic spectrum data {0}".format(get_error_msg(acoustic_spectrum_serializer.errors)), status.HTTP_404_NOT_FOUND

        # except Exception as e:
        #     return "Something went wrong in fft conversion of acoustic data {0}".format(e), status.HTTP_404_NOT_FOUND



        return "All Data Okay", status.HTTP_201_CREATED
    except Exception as e:
        return "Something went wrong. {0}".format(e), status.HTTP_400_BAD_REQUEST



