from celery import shared_task
from time import sleep
from app.SPFunctions.SignalProcessing import getPeak, omegaArithmetic, getRMS, peakDetect, getEnvelope, getPeak_to_peak, bandPassFilter, StatFunctionsAdjustment, highPassFilter, getFilterValues, bandStopFilter
from app.SPFunctions.fftFunctions import getFFT, FFTAnalysisTwoSide, getFFT10K, getFFT20K
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
import requests
import pytz
local_tz = pytz.timezone("Asia/Kolkata") 
utc_tz = pytz.timezone("UTC") 
import random
import base64
import string
from app.cache import get_threshold_data, get_threshold_counter_data, updateThreshCounterDB, get_mount_data, get_sensor_orientation_data, get_sensor_orientation_data_rms_only, check_last_mail_timestamp
from django.template.loader import render_to_string, get_template
from django.core.mail import send_mail, EmailMessage, EmailMultiAlternatives
from django.core.mail import send_mail
from .cache import redis_client_rms_batch

timezone_list = {
  "IN": "Asia/Kolkata",
  "KR": "Asia/Seoul",
  "GB": "Europe/London",
  "AE": "Asia/Dubai"
}

def createRandom(n=5):
    characters = string.ascii_letters + string.digits
    # Generate a random string of 5 characters
    start = ''.join(random.choices(characters, k=n))
    end = ''.join(random.choices(characters, k=n))
    return start, end

@shared_task
def sleepy(duration):
    sleep(duration)
    print("printing from task file after celery job done iiiiiiiiii")
    return None

def updateDbSendMail(
        counter_param_pointer,
        rep_param_pointer,
        comp_key,
        counter_values,
        counter_param,
        threshold_values,
        statFunction,
        stat_values,
        timestamp_param,
        level
        ):

    if level == '1':
        priority = "Alert"
    elif level == '2':
        priority = "Danger"
    elif level == '3':
        priority = "Critical"

    if counter_param_pointer >= rep_param_pointer:
        res = check_last_mail_timestamp(comp_key, round(datetime.datetime.now().timestamp()))
        print("--------------------res-----------------", res)
        
        counter_values[counter_param] = 0
        
        if res.get("status") == True:
            # Send alarm (24 hours have passed since last alarm)
            threshValue = threshold_values.get(statFunction+"_amp_level_"+level)
            observedValue = stat_values.get(statFunction)
            try:
                macID = "_".join(stat_values.get("composite").split("_")[:2])
                deviceMountData = get_mount_data(macID)
                device_location = deviceMountData.get("point_name")+'-'+deviceMountData.get("mount_location")
                device_asset_id = stat_values.get("asset_id")
            except:
                try:
                    deviceMountData = models.DeviceMountMaster.objects.get(id=stat_values.get("mount_id"))
                    device_location = deviceMountData.point_name+'-'+deviceMountData.mount_location
                    device_asset_id = deviceMountData.asset_id
                except:
                    print("Device mount data not found for composite:", stat_values.get("composite"))
                    device_location = "-"
                    device_asset_id = deviceMountData.get("asset_id")

            alarmData = {"composite": stat_values.get("composite"), "signal_type": threshold_values.get("signal_type"), 
                        "trend_type": statFunction+"_amp", "axis": threshold_values.get("axis").lower(), "priority": priority,
                        "sensor_location": device_location, "asset_id": device_asset_id,
                        "timestamp": counter_values[timestamp_param], "threshold_value": threshValue, "observed_value": observedValue}
            alarmHistoryDataSerializer = serializers.AlarmHistoryMasterSerializer(data=alarmData)
            try:
                if alarmHistoryDataSerializer.is_valid():
                    alarmHistoryDataSerializer.save()
                    sendMailSingle.delay(alarmData)
                    print("mail sent function triggered")
                    result = updateThreshCounterDB(comp_key, counter_values)
            except Exception as e3:
                print("exception 3", e3)
                result = updateThreshCounterDB(comp_key, counter_values)
        else:
            print(f"Counter reset to 0 but alarm suppressed (last alarm was within 24 hours)")
            result = updateThreshCounterDB(comp_key, counter_values)
    else:
        # Counter hasn't reached repetition threshold yet, just update DB
        result = updateThreshCounterDB(comp_key, counter_values)

    return True


def checkValuesAgainstThreshold(threshold_values, counter_values, stat_values, statfunctionList, harmonic_values, harmonicsList):

    composite_full = threshold_values.get("composite")
    mount_id = composite_full.split('_')[-1]
    comp_key = str(mount_id) + '-' + threshold_values.get("axis") + '-' + threshold_values.get("signal_type") + '-' + threshold_values.get("domain")
    
    for statFunction in statfunctionList:
        current_value = stat_values.get(statFunction)
        level_3_threshold = threshold_values.get(statFunction+'_amp_level_3', 0)
        level_2_threshold = threshold_values.get(statFunction+'_amp_level_2', 0)
        level_1_threshold = threshold_values.get(statFunction+'_amp_level_1', 0)
        
        # Determine which level the current value is in
        in_level_3 = (level_3_threshold > 0 and current_value >= level_3_threshold)
        in_level_2 = (level_2_threshold > 0 and current_value >= level_2_threshold and not in_level_3)
        in_level_1 = (level_1_threshold > 0 and current_value >= level_1_threshold and not in_level_2 and not in_level_3)
        
        # ============= LEVEL 3 (Critical) =============
        if in_level_3:
            counter_param = statFunction + '_amp_counter_level_3'
            timestamp_param = statFunction + '_amp_repetition_level_3_timestamp'
            
            counter = counter_values.get(counter_param, 0)
            counter_value = counter + 1
            counter_values[counter_param] = counter_value

            try:
                timestamp_value = stat_values.get("timestamp")
                if isinstance(timestamp_value, str):
                    counter_values[timestamp_param] = timestamp_value
                else:
                    counter_values[timestamp_param] = timestamp_value.isoformat()
            except:
                counter_values[timestamp_param] = datetime.datetime.now().isoformat()

            rep_param_pointer = counter_values.get(statFunction + '_amp_repetition_level_3')
            
            updateDbSendMail(
                counter_value, 
                rep_param_pointer, 
                comp_key, 
                counter_values, 
                counter_param, 
                threshold_values,
                statFunction,
                stat_values,
                timestamp_param,
                "3"
            )
            
            # Reset lower level counters since we're in a higher priority zone
            counter_values[statFunction + '_amp_counter_level_2'] = 0
            counter_values[statFunction + '_amp_counter_level_1'] = 0
            counter_values[statFunction + '_amp_repetition_level_2_timestamp'] = datetime.datetime.now().isoformat()
            counter_values[statFunction + '_amp_repetition_level_1_timestamp'] = datetime.datetime.now().isoformat()
            
        else:
            # Not in Level 3, reset its counter
            counter_values[statFunction + '_amp_counter_level_3'] = 0
            counter_values[statFunction + '_amp_repetition_level_3_timestamp'] = datetime.datetime.now().isoformat()
            updateThreshCounterDB(comp_key, counter_values)
        
        # ============= LEVEL 2 (Danger) =============
        if in_level_2:
            counter_param = statFunction + '_amp_counter_level_2'
            timestamp_param = statFunction + '_amp_repetition_level_2_timestamp'
            
            counter = counter_values.get(counter_param, 0)
            counter_value = counter + 1
            counter_values[counter_param] = counter_value

            try:
                timestamp_value = stat_values.get("timestamp")
                if isinstance(timestamp_value, str):
                    counter_values[timestamp_param] = timestamp_value
                else:
                    counter_values[timestamp_param] = timestamp_value.isoformat()
            except:
                counter_values[timestamp_param] = datetime.datetime.now().isoformat()

            rep_param_pointer = counter_values.get(statFunction + '_amp_repetition_level_2')
            
            updateDbSendMail(
                counter_value, 
                rep_param_pointer, 
                comp_key, 
                counter_values, 
                counter_param, 
                threshold_values,
                statFunction,
                stat_values,
                timestamp_param,
                "2"
            )
            
            # Reset lower level counter
            counter_values[statFunction + '_amp_counter_level_1'] = 0
            counter_values[statFunction + '_amp_repetition_level_1_timestamp'] = datetime.datetime.now().isoformat()
            
        else:
            # Not in Level 2, reset its counter (only if not in Level 3)
            if not in_level_3:
                counter_values[statFunction + '_amp_counter_level_2'] = 0
                counter_values[statFunction + '_amp_repetition_level_2_timestamp'] = datetime.datetime.now().isoformat()
                updateThreshCounterDB(comp_key, counter_values)
        
        # ============= LEVEL 1 (Alert) =============
        if in_level_1:
            counter_param = statFunction + '_amp_counter_level_1'
            timestamp_param = statFunction + '_amp_repetition_level_1_timestamp'
            
            counter = counter_values.get(counter_param, 0)
            counter_value = counter + 1
            counter_values[counter_param] = counter_value

            try:
                timestamp_value = stat_values.get("timestamp")
                if isinstance(timestamp_value, str):
                    counter_values[timestamp_param] = timestamp_value
                else:
                    counter_values[timestamp_param] = timestamp_value.isoformat()
            except:
                counter_values[timestamp_param] = datetime.datetime.now().isoformat()

            rep_param_pointer = counter_values.get(statFunction + '_amp_repetition_level_1')
            
            updateDbSendMail(
                counter_value, 
                rep_param_pointer, 
                comp_key, 
                counter_values, 
                counter_param, 
                threshold_values,
                statFunction,
                stat_values,
                timestamp_param,
                "1"
            )
            
        else:
            # Not in Level 1, reset its counter (only if not in Level 2 or 3)
            if not in_level_2 and not in_level_3:
                counter_values[statFunction + '_amp_counter_level_1'] = 0
                counter_values[statFunction + '_amp_repetition_level_1_timestamp'] = datetime.datetime.now().isoformat()

    # ============= HARMONICS PROCESSING =============
    if harmonic_values != None and harmonicsList != None:
        for harmonic in harmonicsList:
            harmonic_key = harmonic + '_amp'
            current_value = harmonic_values.get(harmonic_key)
            
            if current_value is None:
                continue
                
            level_3_threshold = threshold_values.get(harmonic+'_amp_level_3', 0)
            level_2_threshold = threshold_values.get(harmonic+'_amp_level_2', 0)
            level_1_threshold = threshold_values.get(harmonic+'_amp_level_1', 0)
            
            in_level_3 = (level_3_threshold > 0 and current_value >= level_3_threshold)
            in_level_2 = (level_2_threshold > 0 and current_value >= level_2_threshold and not in_level_3)
            in_level_1 = (level_1_threshold > 0 and current_value >= level_1_threshold and not in_level_2 and not in_level_3)
            
            # ============= LEVEL 3 (Critical) =============
            if in_level_3:
                counter_param = harmonic + '_amp_counter_level_3'
                timestamp_param = harmonic + '_amp_repetition_level_3_timestamp'
                
                counter = counter_values.get(counter_param, 0)
                counter_value = counter + 1
                counter_values[counter_param] = counter_value
                
                try:
                    timestamp_value = harmonic_values.get("timestamp")
                    counter_values[timestamp_param] = timestamp_value.isoformat()
                except:
                    counter_values[timestamp_param] = datetime.datetime.now().isoformat()

                rep_param_pointer = counter_values.get(harmonic + '_amp_repetition_level_3')
                
                updateDbSendMail(
                    counter_value, 
                    rep_param_pointer, 
                    comp_key, 
                    counter_values, 
                    counter_param, 
                    threshold_values,
                    harmonic,
                    harmonic_values,
                    timestamp_param,
                    "3"
                )
                
                counter_values[harmonic + '_amp_counter_level_2'] = 0
                counter_values[harmonic + '_amp_counter_level_1'] = 0
                counter_values[harmonic + '_amp_repetition_level_2_timestamp'] = datetime.datetime.now().isoformat()
                counter_values[harmonic + '_amp_repetition_level_1_timestamp'] = datetime.datetime.now().isoformat()
                
            else:
                counter_values[harmonic + '_amp_counter_level_3'] = 0
                counter_values[harmonic + '_amp_repetition_level_3_timestamp'] = datetime.datetime.now().isoformat()
                updateThreshCounterDB(comp_key, counter_values)
            
            # ============= LEVEL 2 (Danger) =============
            if in_level_2:
                counter_param = harmonic + '_amp_counter_level_2'
                timestamp_param = harmonic + '_amp_repetition_level_2_timestamp'
                
                counter = counter_values.get(counter_param, 0)
                counter_value = counter + 1
                counter_values[counter_param] = counter_value

                try:
                    timestamp_value = harmonic_values.get("timestamp")
                    counter_values[timestamp_param] = timestamp_value.isoformat()
                except:
                    counter_values[timestamp_param] = datetime.datetime.now().isoformat()
                
                rep_param_pointer = counter_values.get(harmonic + '_amp_repetition_level_2')
                
                updateDbSendMail(
                    counter_value, 
                    rep_param_pointer, 
                    comp_key, 
                    counter_values, 
                    counter_param, 
                    threshold_values,
                    harmonic,
                    harmonic_values,
                    timestamp_param,
                    "2"
                )
                
                counter_values[harmonic + '_amp_counter_level_1'] = 0
                counter_values[harmonic + '_amp_repetition_level_1_timestamp'] = datetime.datetime.now().isoformat()
                
            else:
                if not in_level_3:
                    counter_values[harmonic + '_amp_counter_level_2'] = 0
                    counter_values[harmonic + '_amp_repetition_level_2_timestamp'] = datetime.datetime.now().isoformat()
                    updateThreshCounterDB(comp_key, counter_values)
            
            # ============= LEVEL 1 (Alert) =============
            if in_level_1:
                counter_param = harmonic + '_amp_counter_level_1'
                timestamp_param = harmonic + '_amp_repetition_level_1_timestamp'
                
                counter = counter_values.get(counter_param, 0)
                counter_value = counter + 1
                counter_values[counter_param] = counter_value

                try:
                    timestamp_value = harmonic_values.get("timestamp")
                    counter_values[timestamp_param] = timestamp_value.isoformat()
                except:
                    counter_values[timestamp_param] = datetime.datetime.now().isoformat()
                
                rep_param_pointer = counter_values.get(harmonic + '_amp_repetition_level_1')
                
                updateDbSendMail(
                    counter_value, 
                    rep_param_pointer, 
                    comp_key, 
                    counter_values, 
                    counter_param, 
                    threshold_values,
                    harmonic,
                    harmonic_values,
                    timestamp_param,
                    "1"
                )
                
            else:
                if not in_level_2 and not in_level_3:
                    counter_values[harmonic + '_amp_counter_level_1'] = 0
                    counter_values[harmonic + '_amp_repetition_level_1_timestamp'] = datetime.datetime.now().isoformat()
                    updateThreshCounterDB(comp_key, counter_values)
    
    return True

    



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
    
    
# @shared_task
# def saveDataAsync(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp):
#     try:
#         RawSerializer = serializers.RawDataMasterSerializer(data=data)
#         if RawSerializer.is_valid():
#             RawSerializer.save()
#             macID = composite_key.split("_")[1]
#             if axis in ['x','y']:
#                 # vibrationDataRawSignal = np.multiply(rData, 0.9)
#                 vibrationDataRawSignal = np.multiply(rData, 0.87)
#             elif axis in ['z']:
#                 vibrationDataRawSignal = np.multiply(rData, 1.03)
#             else:
#                 vibrationDataRawSignal = rData

#             rpm_data = models.SignalProcessingMaster.objects.filter(composite_id=composite_key).values('rpm','high_pass','low_pass')
#             try:
#                 RPM = float(rpm_data[0].get("rpm"))
#             except:
#                 RPM = 0
#             try:
#                 highPass = int(rpm_data[0].get("high_pass"))
#             except:
#                 highPass = 10

#             if axis == "z" and macID in ["E8:31:CD:38:7A:10"]:  #mach id of jinwoo korea
#                 lowPass = 5100
#             else:
#                 try:
#                     lowPass = int(rpm_data[0].get("low_pass"))
#                 except:
#                     lowPass = 6000

#             if macID in ["70:B8:F6:02:49:34"]:
#                 vibrationData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
#             else:
#                 try:
#                     vibrationDataUnFiltered = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
#                     vibrationData = bandPassFilter(vibrationDataUnFiltered,highPass,lowPass,samplingFrequency)
#                 except:
#                     vibrationData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)


#             # vibrationData = vibrationDataRawSignal

#             # vibrationData = vibrationDataUnFiltered
#             # pdb.set_trace()
#             if axis == 'x':
#                 if temp:
#                     tempData = {"composite": composite_key, 'timestamp':local_dt, 'temp': round(temp,2),'asset_id': asset_id}
#                     temp_serializer = serializers.TemperatureMasterSerializer(data=tempData)
#                     if temp_serializer.is_valid():
#                         temp_serializer.save()

#             # if axis == 'x':
#             #     vibrationData = vibrationData-0.03
#             # elif axis in ['y','z']:
#             #     vibrationData = vibrationData-0.04
#             # else:
#             #     vibrationData = vibrationData


#             accelerationTWF, accelerationSptrm, velocityTWF, velocitySptrm, displacementTWF, displacementSptrm, f_acc, f_vel, f_dis, twf = omegaArithmetic(vibrationData, macID, int(samplingFrequency))
#             velocity_twf_rms = getRMS(velocityTWF)
#             velocity_sptrm_rms = getRMS(velocitySptrm)
#             acc_twf = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(accelerationTWF),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
#             acc_sptrm = {"high_pass": highPass, "low_pass": lowPass, "rpm": RPM, "timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(accelerationSptrm),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
#             vel_twf = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"velocity_rms":velocity_twf_rms,"data":list(velocityTWF),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
#             vel_sptrm = {"high_pass": highPass, "low_pass": lowPass, "rpm": RPM, "timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"velocity_rms":velocity_sptrm_rms,"data":list(velocitySptrm),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
#             dis_twf = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(displacementTWF),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
#             dis_sptrm = {"high_pass": highPass, "low_pass": lowPass, "rpm": RPM, "timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":list(displacementSptrm),"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}
#             spectrum_x_axis_data = {"composite":composite_key,"asset_id":asset_id, "timestamp":local_dt ,"acceleration":f_acc,"velocity":f_vel,"displacement":f_dis}
            


#             # ********************************** Acceleration Envelope Calculations **********************************

#             try:
#                 try:
#                     high_pass_value, low_pass_value = getFilterValues(int(samplingFrequency), axis)
#                 except:
#                     high_pass_value = 500
#                     low_pass_value = 6000
#                 envRawData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
#                 filteredEnvRawData = bandPassFilter(envRawData,high_pass_value, low_pass_value, int(samplingFrequency))
#                 accTwfEnvelope = getEnvelope(filteredEnvRawData)
#                 accSptrmEnvelope, _ = getFFT(accTwfEnvelope, samplingFrequency)
#             except:
#                 accTwfEnvelope = []
#                 accSptrmEnvelope = []

#             accTwfEnvelope_data = {"composite":composite_key, 'timestamp':local_dt, 'fs':samplingFrequency,"no_of_samples": no_of_samples,\
#                                 'data':accTwfEnvelope,'axis':axisOrientation,'asset_id':asset_id}
#             accSptrmEnvelope_data = {"composite":composite_key, 'timestamp':local_dt, 'fs':samplingFrequency,"no_of_samples": no_of_samples,\
#                                 'data':accSptrmEnvelope,'axis':axisOrientation,'asset_id':asset_id}
            


#             # ********************************** Auto Correlation Calculations **********************************
            
#             # try:
#             #     autoCorr = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
#             #     filteredAutoCorr = bandPassFilter(autoCorr,500, 6000, int(samplingFrequency))
#             #     envelopeAutoCorr = getEnvelope(filteredAutoCorr)
#             #     auto_corr = getAutoCorrelation(envelopeAutoCorr)
#             # except:
#             #     auto_corr = []
            
#             # autoCorrData = {"timestamp":local_dt,"fs":samplingFrequency,"no_of_samples": no_of_samples,"data":auto_corr,"axis":axisOrientation,"composite":composite_key,"asset_id":asset_id}


#             # ********************************** Phase value calculations (common for all) **********************************
#             # RPM = 2000

#             try:
#                 # pdb.set_trace()
#                 peakValue = max(dis_twf.get("data"))
#                 peakValueIndex = list(dis_twf.get("data")).index(peakValue)
#                 if int(twf[peakValueIndex]/(60/RPM)*360) > 90:
#                     phase = round(360+(90-(twf[peakValueIndex]/((60/RPM)*360))),2)
#                 else:
#                     phase = round(90-(twf[peakValueIndex]/((60/RPM)*360)),2)

#             except:
#                 phase = 0

#             # ********************************** Acceleration Harmonics **********************************
#             try:
#                 # pdb.set_trace()
#                 if RPM > 0:
#                     f_rpm = RPM/60  # using for IMF data only, need to make dynamic from database (config app)
#                     row = len(accelerationSptrm)*2
#                     accelerationPeaks = []
#                     accelerationPeakFrequency = []
#                     for index in np.arange(5):
#                         if index in [1,2]:
#                             f_desired = (f_acc>=(f_rpm*(index+1)-2*(samplingFrequency/row))) & (f_acc<=(f_rpm*(index+1)+2*(samplingFrequency/row)))
#                         elif index in [3,4]:
#                             f_desired = (f_acc>=(f_rpm*(index+1)-3*(samplingFrequency/row))) & (f_acc<=(f_rpm*(index+1)+3*(samplingFrequency/row)))
#                         else:
#                             f_desired = (f_acc>=(f_rpm*(index+1)-(samplingFrequency/row))) & (f_acc<=(f_rpm*(index+1)+(samplingFrequency/row)))
#                         vel_peak, vel_peak_axis = peakDetect(accelerationSptrm,f_acc,f_desired)
#                         accelerationPeaks.append(round(vel_peak,3))
#                         peak_value_index = np.where(f_acc == vel_peak_axis)
#                         accelerationPeakFrequency.append(peak_value_index[0][0])

#                     acceleration_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
#                     'phase':phase,'one_amp':accelerationPeaks[0],'one_freq':accelerationPeakFrequency[0],\
#                     'two_amp':accelerationPeaks[1],'two_freq':accelerationPeakFrequency[1],'three_amp':accelerationPeaks[2],\
#                     'three_freq':accelerationPeakFrequency[2],'four_amp':accelerationPeaks[3],'four_freq':accelerationPeakFrequency[3],\
#                     'five_amp':accelerationPeaks[4],'five_freq':accelerationPeakFrequency[4], 'asset_id':asset_id}
#                 else:
#                     acceleration_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
#                                 'phase':phase,'one_amp':0,'one_freq':0,'two_amp':0,'two_freq':0,'three_amp':0,\
#                                 'three_freq':0,'four_amp':0,'four_freq':0,'five_amp':0,'five_freq':0,'asset_id':asset_id}
#             except:
#                 acceleration_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
#                                 'phase':phase,'one_amp':0,'one_freq':0,'two_amp':0,'two_freq':0,'three_amp':0,\
#                                 'three_freq':0,'four_amp':0,'four_freq':0,'five_amp':0,'five_freq':0,'asset_id':asset_id}

#             # ********************************** Velocity Harmonics **********************************

#             try:
#                 if RPM > 0:
#                     f_rpm = RPM/60 
#                     row = len(velocitySptrm)*2
#                     velocityPeaks = []
#                     velocityPeakFrequency = []
#                     for index in np.arange(5):
#                         if index in [1,2]:
#                             f_desired = (f_vel>=(f_rpm*(index+1)-2*(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+2*(samplingFrequency/row)))
#                         elif index in [3,4]:
#                             f_desired = (f_vel>=(f_rpm*(index+1)-3*(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+3*(samplingFrequency/row)))
#                         else:
#                             f_desired = (f_vel>=(f_rpm*(index+1)-(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+(samplingFrequency/row)))
#                         vel_peak, vel_peak_axis = peakDetect(velocitySptrm,f_vel,f_desired)
#                         velocityPeaks.append(round(vel_peak,3))
#                         peak_value_index = np.where(f_vel == vel_peak_axis)
#                         velocityPeakFrequency.append(peak_value_index[0][0])

#                     velocity_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
#                                         'phase':phase,'one_amp':velocityPeaks[0],'one_freq':velocityPeakFrequency[0],\
#                                         'two_amp':velocityPeaks[1],'two_freq':velocityPeakFrequency[1],'three_amp':velocityPeaks[2],\
#                                         'three_freq':velocityPeakFrequency[2],'four_amp':velocityPeaks[3],'four_freq':velocityPeakFrequency[3],\
#                                         'five_amp':velocityPeaks[4],'five_freq':velocityPeakFrequency[4],'asset_id':asset_id}
#                 else:
#                     velocity_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
#                                 'phase':phase,'one_amp':0,'one_freq':0,'two_amp':0,'two_freq':0,'three_amp':0,\
#                                 'three_freq':0,'four_amp':0,'four_freq':0,'five_amp':0,'five_freq':0,'asset_id':asset_id}
#             except:
#                 velocity_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
#                                 'phase':phase,'one_amp':0,'one_freq':0,'two_amp':0,'two_freq':0,'three_amp':0,\
#                                 'three_freq':0,'four_amp':0,'four_freq':0,'five_amp':0,'five_freq':0,'asset_id':asset_id}


#             # ********************************** Velocity Harmonics for diagnostics **********************************
           
#             # try:
#             #     # pdb.set_trace()
#             #     final_result = getHarmonicFamilies(velocitySptrm, f_vel)
#             #     velocity_auto_harmonics_data = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation, "data": final_result, "asset_id": asset_id}
#             #     if RPM > 0:
#             #         fundamental_frequency = round(RPM/60, 3)
#             #         max_difference = 1.7
#             #         # closest keys to find frequency near fundamental frequency for 1X
#             #         closest_keys = [key for key in final_result.keys() if abs(key - fundamental_frequency) <= max_difference]
#             #         if len(closest_keys) > 0:
#             #             closest_key = min(closest_keys)
#             #             closest_values = final_result[closest_key]
                       
#             #             found_frequencies, zero_indices = insert_missing_multiples(closest_values.get("freq"), 5)     # completing harmonic series upto 10x and inserting 0 where frequency missing
#             #             updated_amplitudes = insert_zeros_amp(closest_values.get("amp"), zero_indices)                # inserting zero to amplitude list where frequency is missing
#             #             updated_indices = insert_zeros_amp(closest_values.get("index"), zero_indices)                 # inserting zero to indexes list where frequency is missing
#             #             # one_amp = closest_values.get("amp")[0], 
#             #             diagnostics_value_data = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation, "asset_id": asset_id,\
#             #                                         "one_amp": updated_amplitudes[0], "two_amp": updated_amplitudes[1], "three_amp": updated_amplitudes[2], \
#             #                                             "four_amp": updated_amplitudes[3], "five_amp": updated_amplitudes[4], "six_amp": updated_amplitudes[5], \
#             #                                                 "seven_amp": updated_amplitudes[6], "eight_amp": updated_amplitudes[7], "nine_amp": updated_amplitudes[8], \
#             #                                                     "ten_amp": updated_amplitudes[9], "signal_type": "velocity", \
#             #                                                         "four_to_seven_amp": updated_amplitudes[4]+updated_amplitudes[5]+updated_amplitudes[6]+updated_amplitudes[7]}
#             #             diagnostics_value_data_serializer = serializers.DiagnosticsValuesMasterSerializer(data=diagnostics_value_data)
#             #             if diagnostics_value_data_serializer.is_valid():
#             #                 diagnostics_value_data_serializer.save()
#             #             else:
#             #                 pass
#             #     else:
#             #         pass
#             # except:
#             #     velocity_auto_harmonics_data = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation, "data": final_result, "asset_id": asset_id}

#             # ********************************** Displacement Harmonics **********************************
#             # try:
#             #     f_rpm = RPM/60  # using for IMF data only, need to make dynamic from database (config app)
#             #     row = len(displacementSptrm)
#             #     displacementPeaks = []
#             #     displacementPeakFrequency = []
#             #     for index in np.arange(10):
#             #         f_desired = (f_vel>=(f_rpm*(index+1)-(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+(samplingFrequency/row)))
#             #         vel_peak, vel_peak_axis = peakDetect(displacementSptrm,f_vel,f_desired)
#             #         displacementPeaks.append(round(vel_peak,3))
#             #         peak_value_index = np.where(f_vel == vel_peak_axis)
#             #         displacementPeakFrequency.append(peak_value_index[0][0])
#             # except:
#             #     pass

#             # displacement_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
#             #                     'phase':phase,'one_amp':displacementPeaks[0],'one_freq':displacementPeakFrequency[0],\
#             #                     'two_amp':displacementPeaks[1],'two_freq':displacementPeakFrequency[1],'three_amp':displacementPeaks[2],\
#             #                     'three_freq':displacementPeakFrequency[2],'four_amp':displacementPeaks[3],'four_freq':displacementPeakFrequency[3],\
#             #                     'five_amp':displacementPeaks[4],'five_freq':displacementPeakFrequency[4],'six_amp':displacementPeaks[5],\
#             #                     'six_freq':displacementPeakFrequency[5],'seven_amp':displacementPeaks[6],'seven_freq':displacementPeakFrequency[6],\
#             #                     'eight_amp':displacementPeaks[7],'eight_freq':displacementPeakFrequency[7],'nine_amp':displacementPeaks[8],\
#             #                     'nine_freq':displacementPeakFrequency[8],'ten_amp':displacementPeaks[9],'ten_freq':displacementPeakFrequency[9],\
#             #                     'asset_id':asset_id}



            
#             # ********************************** Acceleration Envelope (both time & freq) **********************************
#             # ********************************** High pass filter for envelope only for nbc data set **********************************
#             # if macID == 'wl_22':
#             #     try:
#             #         vibrationDataRaw - np.mean(vibrationDataRaw)
#             #         accelerationTWF_filtered = bandPassFilter(vibrationDataRaw,1000,2000,samplingFrequency)
#             #         accTwfEnvelope = getEnvelope(accelerationTWF_filtered)
#             #         accSptrmEnvelope, _ = getFFT(accTwfEnvelope, samplingFrequency)
#             #     except:
#             #         accTwfEnvelope = []
#             #         accSptrmEnvelope = []
#             # else:
            


#             # ********************************** acceleration statistical parameters **********************************
#             try:
#                 acceleration_time_rms_org = getRMS(accelerationTWF)
#                 # acceleration_time_rms = round(acceleration_time_rms_org, 2)

#                 if macID in ["70:B8:F6:02:49:34"]:
#                     acceleration_time_rms = round(acceleration_time_rms_org, 2)
#                 else:
#                     acceleration_time_rms = StatFunctionsAdjustment(acceleration_time_rms_org, 'acceleration', axis, 'rms')

#                 acceleration_time_peak = getPeak(accelerationTWF)
#                 acceleration_time_peak_to_peak = getPeak_to_peak(accelerationTWF)
#                 # acceleration_time_peak = acceleration_time_rms * 1.414
#                 # acceleration_time_peak_to_peak = acceleration_time_peak * 2
#             except:
#                 acceleration_time_rms = 0
#                 acceleration_time_peak = 0
#                 acceleration_time_peak_to_peak = 0


#             try:
#                 acceleration_time_kurtosis = kurtosis(np.array(accelerationTWF))
#             except:
#                 acceleration_time_kurtosis = 0

#             dataAccelerationStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(acceleration_time_kurtosis,2),"rms":acceleration_time_rms,"axis":axisOrientation,\
#                                     "composite":composite_key,"asset_id":asset_id,"peak":round(acceleration_time_peak,2),"peak_to_peak":round(acceleration_time_peak_to_peak,2)}

#             # ********************************** velocity statistical parameters **********************************
#             try:
#                 # pdb.set_trace()
#                 velocity_time_rms_org = getRMS(velocityTWF)
#                 # velocity_time_rms = round(velocity_time_rms_org, 2)

#                 if macID in ["70:B8:F6:02:49:34"]:
#                     velocity_time_rms = round(velocity_time_rms_org, 2)
#                 else:
#                     velocity_time_rms = StatFunctionsAdjustment(velocity_time_rms_org, 'velocity', axis, 'rms')

#                 velocity_time_peak = getPeak(velocityTWF)
#                 velocity_time_peak_to_peak = getPeak_to_peak(velocityTWF)
#                 # velocity_time_peak = velocity_time_rms * 1.414
#                 # velocity_time_peak_to_peak = velocity_time_peak * 2

#             except:
#                 velocity_time_rms = 0
#                 velocity_time_peak = 0
#                 velocity_time_peak_to_peak = 0


#             try:
#                 velocity_time_kurtosis = kurtosis(np.array(velocityTWF))
#             except:
#                 velocity_time_kurtosis = 0

#             dataVelocityStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(velocity_time_kurtosis,2),"rms":velocity_time_rms,"axis":axisOrientation,\
#                                         "composite":composite_key,"asset_id":asset_id,"peak":round(velocity_time_peak,2),"peak_to_peak":round(velocity_time_peak_to_peak,2)}


#             # ********************************** displacement statistical parameters **********************************
#             try:
#                 displacement_time_rms_org = getRMS(displacementTWF)
#                 # displacement_time_rms = round(displacement_time_rms_org, 2)

#                 if macID in ["70:B8:F6:02:49:34"]:
#                     displacement_time_rms = round(displacement_time_rms_org, 2)
#                 else:
#                     displacement_time_rms = StatFunctionsAdjustment(displacement_time_rms_org, 'displacement', axis, 'rms')

#                 displacement_time_peak = getPeak(displacementTWF)
#                 displacement_time_peak_to_peak = getPeak_to_peak(displacementTWF)
#                 # displacement_time_peak = displacement_time_rms * 1.414
#                 # displacement_time_peak_to_peak = displacement_time_peak * 2
#             except:
#                 displacement_time_rms = 0
#                 displacement_time_peak = 0
#                 displacement_time_peak_to_peak = 0


#             try:
#                 displacement_time_kurtosis = kurtosis(np.array(displacementTWF))
#             except:
#                 displacement_time_kurtosis = 0

#             dataDisplacementStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(displacement_time_kurtosis,2),"rms":displacement_time_rms,"axis":axisOrientation,\
#                                         "composite":composite_key,"asset_id":asset_id,"peak":round(displacement_time_peak,2),"peak_to_peak":round(displacement_time_peak_to_peak,2)}



#             # ********************************** EHNR Calculations **********************************
#             try:
#                 ehnr = EHNR(np.array(vibrationData), samplingFrequency)
#                 ehnrData = {"composite": composite_key,"timestamp": local_dt,"ehnr": round(ehnr, 2),"axis": axisOrientation,"asset_id": asset_id}
#             except:
#                 ehnrData = {"composite": composite_key,"timestamp": local_dt,"ehnr": 0,"axis": axisOrientation,"asset_id": asset_id}



#             # ********************************** Bearing Fault Frequencies **********************************

#             try:
#                 bearingInstance = models.BearingDetailMaster.objects.get(mount_id=mount_id)
#                 bearingData = model_to_dict(bearingInstance)
#             except:
#                 bearingData = {"bpfo": None,"bpfi": None,"bsf": None,"ftf": None}

#             # ********************************** Acceleration Spectrum Bearing Fault Frequencies **********************************
#             bff_data_acc = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation,  "signal_type": "Acceleration",  "asset_id":asset_id }
#             for falutFrequency in ['bpfo','bpfi','bsf','ftf']:
#                 if bearingData.get(falutFrequency):
#                     if falutFrequency == 'bsf':
#                         BFF = float(bearingData.get(falutFrequency)) * (RPM/60) *2
#                     else:
#                         BFF = float(bearingData.get(falutFrequency)) * (RPM/60)
#                     f_acc = np.array(f_acc)
#                     peaks_acc = []
#                     peak_frequence_acc = []
#                     row_acc = len(accelerationSptrm)*2

#                     for index in range(1,6,1):
#                         try:
#                             f_desired = (f_acc>=(BFF*(index)-(samplingFrequency/row_acc))) & (f_acc<=(BFF*(index)+(samplingFrequency/row_acc)))
#                             acc_peak, acc_peak_axis = peakDetect(accelerationSptrm,f_acc,f_desired)
#                             peaks_acc.append(round(float(acc_peak),3))
#                             peak_value_index = np.where(f_acc == acc_peak_axis)
#                             peak_frequence_acc.append(peak_value_index[0][0])
#                             bff_data_acc.update({falutFrequency+"_amp": peaks_acc, falutFrequency+"_freq": peak_frequence_acc})
#                         except:
#                             pass
#                 else:
#                     bff_data_acc.update({falutFrequency+"_amp": [], falutFrequency+"_freq": []})

#             # ********************************** Velocity Spectrum Bearing Fault Frequencies **********************************
#             bff_data_vel = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation,  "signal_type": "Velocity",  "asset_id":asset_id }
#             for falutFrequency in ['bpfo','bpfi','bsf','ftf']:
#                 if bearingData.get(falutFrequency):
#                     BFF = float(bearingData.get(falutFrequency)) * (RPM/60)
#                     f_vel = np.array(f_vel)
#                     peak_vel = []
#                     peak_frequency_vel = []
#                     row_vel = len(velocitySptrm)*2

#                     for index in range(1,6,1):
#                         try:
#                             f_desired = (f_vel>=(BFF*(index)-(samplingFrequency/row_vel))) & (f_vel<=(BFF*(index)+(samplingFrequency/row_vel)))
#                             vel_peak, vel_peak_axis = peakDetect(velocitySptrm,f_vel,f_desired)
#                             peak_vel.append(round(float(vel_peak),3))
#                             peak_value_index = np.where(f_vel == vel_peak_axis)
#                             peak_frequency_vel.append(peak_value_index[0][0])
#                             bff_data_vel.update({falutFrequency+"_amp": peak_vel, falutFrequency+"_freq": peak_frequency_vel})
#                         except:
#                             pass
#                 else:
#                     bff_data_vel.update({falutFrequency+"_amp": [], falutFrequency+"_freq": []})
            
#             finalDataBFF = [bff_data_acc, bff_data_vel]

#             # ********************************** Check current values against saved threshold values and update counter **********************************
#             # composite + '-' + axis + '-' + signal_type + '-' + domain
#             try:
#                 signalTypeList = ['acceleration', 'velocity', 'temp']
#                 for signal in signalTypeList:
#                     # if signal == 'temp':
#                         # print("-----------------temp------------------",signal, tempData)
#                     # comp_key = composite_key + '-' + axisOrientation + '-' + signal + '-time'
#                     if signal in ['acceleration', 'velocity']:
#                         threshold_data = get_threshold_data(composite_key, axisOrientation, signal, 'time')
#                         threshold_counter_data = get_threshold_counter_data(composite_key, axisOrientation, signal, 'time')
#                         if threshold_data != None and threshold_counter_data != None:
#                             if signal == 'acceleration':
#                                 statfunctionList = ['rms', 'peak', 'peak_to_peak']
#                                 harmonicsList = ['one', 'two', 'three', 'four']
#                                 checkValuesAgainstThreshold(threshold_data, threshold_counter_data, dataAccelerationStatTimeMaster, statfunctionList, acceleration_harmonics_data, harmonicsList)
#                             if signal == 'velocity':
#                                 statfunctionList = ['rms', 'peak', 'peak_to_peak']
#                                 harmonicsList = ['one', 'two', 'three', 'four']
#                                 checkValuesAgainstThreshold(threshold_data, threshold_counter_data, dataVelocityStatTimeMaster, statfunctionList, velocity_harmonics_data, harmonicsList)
#                     if signal == 'temp' and axis == 'x':
#                         threshold_data = get_threshold_data(composite_key, 'temp', signal, 'time')
#                         threshold_counter_data = get_threshold_counter_data(composite_key, 'temp', signal, 'time')
#                         if threshold_data != None and threshold_counter_data != None:
#                             statfunctionList = ['temp']
#                             checkValuesAgainstThreshold(threshold_data, threshold_counter_data, tempData, statfunctionList, None, None)

#             except Exception as thresh_e:
#                 print("some exception in thresh_e",signal, thresh_e)


#             accTWFSerializer = serializers.AccelerationTWFMasterSerializer(data=acc_twf)
#             if accTWFSerializer.is_valid():
#                 accSptrmSerializer = serializers.AccelerationSpectrumMasterSerializer(data=acc_sptrm)
#                 if accSptrmSerializer.is_valid():
#                     velocityTWFSerializer = serializers.VelocityTWFMasterSerializer(data=vel_twf)
#                     if velocityTWFSerializer.is_valid():
#                         velocitySptrmSerializer = serializers.VelocitySpectrumMasterSerializer(data=vel_sptrm)
#                         if velocitySptrmSerializer.is_valid():
#                             displacementTWFSerializer = serializers.DisplacementTWFMasterSerializer(data=dis_twf)
#                             if displacementTWFSerializer.is_valid():
#                                 displacementSptrmSerializer = serializers.DisplacementSpectrumMasterSerializer(data=dis_sptrm)
#                                 if displacementSptrmSerializer.is_valid():
#                                     acceleration_harmonics_serializer = serializers.AccelerationHarmonicsMasterSerializer(data=acceleration_harmonics_data)
#                                     if acceleration_harmonics_serializer.is_valid():
#                                         velocity_harmonics_serializer = serializers.VelocityHarmonicsMasterSerializer(data=velocity_harmonics_data)
#                                         if velocity_harmonics_serializer.is_valid():
#                                             # velocity_auto_harmonics_data_serializer = serializers.AutoVelocityHarmonicsMasterSerializer(data=velocity_auto_harmonics_data)
#                                             # if velocity_auto_harmonics_data_serializer.is_valid():
#                                                 spectrum_data_serializer = serializers.SpectrumChartDataMasterSerializer(data=spectrum_x_axis_data)
#                                                 if spectrum_data_serializer.is_valid():
#                                                     # health_serializer = serializers.DeviceHealthStatusSerializer(data=device_health_data)
#                                                     # if health_serializer.is_valid():
#                                                         accTwfEnvelope_serializer = serializers.EnvelopeTWFMasterSerializer(data=accTwfEnvelope_data)
#                                                         if accTwfEnvelope_serializer.is_valid():
#                                                             accSptrmEnvelope_serializer = serializers.EnvelopeSpectrumMasterSerializer(data=accSptrmEnvelope_data)
#                                                             if accSptrmEnvelope_serializer.is_valid():
#                                                                 acceleration_stat_time_serializer = serializers.AccelerationStatTimeMasterSerializer(data=dataAccelerationStatTimeMaster)
#                                                                 if acceleration_stat_time_serializer.is_valid():
#                                                                     # auto_correlation_serializer = serializers.AutoCorrelationMasterSerializer(data=autoCorrData)
#                                                                     # if auto_correlation_serializer.is_valid():
#                                                                         velocity_stat_time_serializer = serializers.VelocityStatTimeMasterSerializer(data=dataVelocityStatTimeMaster)
#                                                                         if velocity_stat_time_serializer.is_valid():
#                                                                             # velocity_stat_freq_serializer = serializers.VelocityStatFreqMasterSerializer(data=dataVelocityStatFreqMaster)
#                                                                             # if velocity_stat_freq_serializer.is_valid():
#                                                                                 displacement_stat_time_serializer = serializers.DisplacementStatTimeMasterSerializer(data=dataDisplacementStatTimeMaster)
#                                                                                 if displacement_stat_time_serializer.is_valid():
#                                                                                     # displacement_stat_freq_serializer = serializers.DisplacementStatFreqMasterSerializer(data=dataDisplacementStatFreqMaster)
#                                                                                     # if displacement_stat_freq_serializer.is_valid():
#                                                                                     bff_serializer = serializers.BearingFaultFrequenciesMasterSerializer(data = finalDataBFF, many=True)
#                                                                                     if bff_serializer.is_valid():
#                                                                                         ehnr_serializer = serializers.FrequencyDomainFeatuersSerializer(data = ehnrData)
#                                                                                         if ehnr_serializer.is_valid():
#                                                                                             accTWFSerializer.save()
#                                                                                             accSptrmSerializer.save()
#                                                                                             velocityTWFSerializer.save()
#                                                                                             velocitySptrmSerializer.save()
#                                                                                             displacementTWFSerializer.save()
#                                                                                             displacementSptrmSerializer.save()
#                                                                                             acceleration_harmonics_serializer.save()
#                                                                                             velocity_harmonics_serializer.save()
#                                                                                             # velocity_auto_harmonics_data_serializer.save()
#                                                                                             spectrum_data_serializer.save()
#                                                                                             # health_serializer.save()
#                                                                                             accTwfEnvelope_serializer.save()
#                                                                                             accSptrmEnvelope_serializer.save()
#                                                                                             acceleration_stat_time_serializer.save()
#                                                                                             # auto_correlation_serializer.save()
#                                                                                             velocity_stat_time_serializer.save()
#                                                                                             # velocity_stat_freq_serializer.save()
#                                                                                             displacement_stat_time_serializer.save()
#                                                                                             # displacement_stat_freq_serializer.save()
#                                                                                             bff_serializer.save()
#                                                                                             ehnr_serializer.save()
#                                                                                             return "All Data Saved", status.HTTP_201_CREATED
#                                                                                         return get_error_msg(ehnr_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                                                     return get_error_msg(bff_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                                                     # return get_error_msg(displacement_stat_freq_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                                                 return get_error_msg(displacement_stat_time_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                                             # return get_error_msg(velocity_stat_freq_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                                         return get_error_msg(velocity_stat_time_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                                     # return get_error_msg(auto_correlation_serializer), status.HTTP_400_BAD_REQUEST
#                                                                 return get_error_msg(acceleration_stat_time_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                             return get_error_msg(accSptrmEnvelope_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                         return get_error_msg(accTwfEnvelope_serializer.errors), status.HTTP_400_BAD_REQUEST                                
#                                                     # return get_error_msg(health_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                                 return get_error_msg(spectrum_data_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                             # return get_error_msg(velocity_auto_harmonics_data_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                         return get_error_msg(velocity_harmonics_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                     return get_error_msg(acceleration_harmonics_serializer.errors), status.HTTP_400_BAD_REQUEST
#                                 return get_error_msg(displacementSptrmSerializer.errors), status.HTTP_400_BAD_REQUEST
#                             return get_error_msg(displacementTWFSerializer.errors), status.HTTP_400_BAD_REQUEST
#                         return get_error_msg(velocitySptrmSerializer.errors), status.HTTP_400_BAD_REQUEST
#                     return get_error_msg(velocityTWFSerializer.errors), status.HTTP_400_BAD_REQUEST
#                 return get_error_msg(accSptrmSerializer.errors), status.HTTP_400_BAD_REQUEST
#             return get_error_msg(accTWFSerializer.errors), status.HTTP_400_BAD_REQUEST
#             # except:
#             #     return "Only Raw Data saved", status.HTTP_400_BAD_REQUEST
#         else:
#             return get_error_msg(RawSerializer.errors), status.HTTP_400_BAD_REQUEST
#     except:
#         return "Something went wrong.", status.HTTP_400_BAD_REQUEST







@shared_task(queue='defaultQueue')
def saveDataAsync(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp):
    
    try:
        RawSerializer = serializers.RawDataMasterSerializer(data=data)
        if RawSerializer.is_valid():
            RawSerializer.save()
            # print("raw data saved in async--------------------------------------------------------------------------------------------",data)
            macID = composite_key.split("_")[1]
            acc_stat = False
            vel_stat = False
            dis_stat = False
            if axis in ['x','y']:
                # vibrationDataRawSignal = np.multiply(rData, 0.9)
                vibrationDataRawSignal = np.multiply(rData, 0.87)
            # elif axis in ['z']:
            #     vibrationDataRawSignal = np.multiply(rData, 1.03)
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
                    tempData = {"composite": composite_key, 'timestamp':local_dt, 'temp': round(temp,2),'asset_id': asset_id, 'mount_id': mount_id}
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

            # try:
            #     # pdb.set_trace()
            #     peakValue = max(dis_twf.get("data"))
            #     peakValueIndex = list(dis_twf.get("data")).index(peakValue)
            #     if int(twf[peakValueIndex]/(60/RPM)*360) > 90:
            #         phase = round(360+(90-(twf[peakValueIndex]/((60/RPM)*360))),2)
            #     else:
            #         phase = round(90-(twf[peakValueIndex]/((60/RPM)*360)),2)

            # except:
            phase = 0

            # ********************************** Acceleration Harmonics **********************************
            acceleration_harmonics_data = None
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
                    'five_amp':accelerationPeaks[4],'five_freq':accelerationPeakFrequency[4], 'asset_id':asset_id, 'mount_id':mount_id}

                    acceleration_harmonics_data_serializer = serializers.AccelerationHarmonicsMasterSerializer(data=acceleration_harmonics_data)
                    if acceleration_harmonics_data_serializer.is_valid():
                        acceleration_harmonics_data_serializer.save()
                    else:
                        acc_err = get_error_msg(acceleration_harmonics_data_serializer.errors)
                        print("Error in acceleration_harmonics_data_serializer", acc_err)
            except Exception as acc_har_exception:
                print("Exception in acceleration harmonics", acc_har_exception)
                

            # ********************************** Velocity Harmonics **********************************
            velocity_harmonics_data = None
            try:
                if RPM > 0:
                    f_rpm = RPM/60 
                    row = len(velocitySptrm)*2
                    velocityPeaks = []
                    velocityPeakFrequency = []
                    for index in np.arange(5):
                        if index in [1,2]:
                            f_desired = (f_vel>=(f_rpm*(index+1)-2*(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+2*(samplingFrequency/row)))
                        elif index in [3,4]:
                            f_desired = (f_vel>=(f_rpm*(index+1)-3*(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+3*(samplingFrequency/row)))
                        else:
                            f_desired = (f_vel>=(f_rpm*(index+1)-(samplingFrequency/row))) & (f_vel<=(f_rpm*(index+1)+(samplingFrequency/row)))
                        vel_peak, vel_peak_axis = peakDetect(velocitySptrm,f_vel,f_desired)
                        velocityPeaks.append(round(vel_peak,3))
                        peak_value_index = np.where(f_vel == vel_peak_axis)
                        velocityPeakFrequency.append(peak_value_index[0][0])

                    velocity_harmonics_data = {"composite":composite_key,'timestamp':local_dt,'axis':axisOrientation,\
                                        'phase':phase,'one_amp':velocityPeaks[0],'one_freq':velocityPeakFrequency[0],\
                                        'two_amp':velocityPeaks[1],'two_freq':velocityPeakFrequency[1],'three_amp':velocityPeaks[2],\
                                        'three_freq':velocityPeakFrequency[2],'four_amp':velocityPeaks[3],'four_freq':velocityPeakFrequency[3],\
                                        'five_amp':velocityPeaks[4],'five_freq':velocityPeakFrequency[4],'asset_id':asset_id, 'mount_id':mount_id}
                    
                    velocity_harmonics_data_serializer = serializers.VelocityHarmonicsMasterSerializer(data=velocity_harmonics_data)
                    if velocity_harmonics_data_serializer.is_valid():
                        velocity_harmonics_data_serializer.save()
                    else:
                        vel_err = get_error_msg(velocity_harmonics_data_serializer.errors)
                        print("Error in velocity_harmonics_data_serializer", vel_err)
            except Exception as vel_har_exception:
                print("Exception in velocity harmonics", vel_har_exception)
                


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
                acceleration_time_kurtosis = kurtosis(np.array(accelerationTWF))
            except:
                acceleration_time_kurtosis = 0

            try:
                acceleration_time_rms_org = getRMS(accelerationTWF)
                # acceleration_time_rms = round(acceleration_time_rms_org, 2)

                if macID in ["70:B8:F6:02:49:34"]:
                    acceleration_time_rms = round(acceleration_time_rms_org, 2)
                else:
                    acceleration_time_rms = StatFunctionsAdjustment(acceleration_time_rms_org, 'acceleration', axis, 'rms')
                
                """piezo sensor rms adjustments"""
                if macID == "CC:7B:5C:37:0B:40":
                    acceleration_time_rms = acceleration_time_rms - 0.03


                acceleration_time_peak = getPeak(accelerationTWF)
                acceleration_time_peak_to_peak = getPeak_to_peak(accelerationTWF)

            except:
                acceleration_time_rms = 0
                acceleration_time_peak = 0
                acceleration_time_peak_to_peak = 0

            # Build axis-specific field names for AccelerationStatTimeOptimized model
            dataAccelerationStatTimeMasterUpdated = {
                "timestamp": local_dt,
                "composite": composite_key,
                "asset_id": asset_id,
                "mount_id": mount_id,
                f"rms_{axisOrientation}": acceleration_time_rms,
                f"peak_{axisOrientation}": round(acceleration_time_peak, 2),
                f"peak_to_peak_{axisOrientation}": round(acceleration_time_peak_to_peak, 2),
                f"kurtosis_{axisOrientation}": round(acceleration_time_kurtosis, 2)
            }

            dataAccelerationStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(acceleration_time_kurtosis,2),"rms":acceleration_time_rms,"axis":axisOrientation,\
                                    "composite":composite_key,"asset_id":asset_id,"peak":round(acceleration_time_peak,2),"peak_to_peak":round(acceleration_time_peak_to_peak,2), 'mount_id':mount_id}


            try:
                obj, created = models.AccelerationStatTimeOptimized.objects.update_or_create(
                    mount_id=mount_id,
                    timestamp=local_dt,
                    defaults=dataAccelerationStatTimeMasterUpdated
                )
                acc_stat = True
                
            except Exception as ee:
                acc_stat = False
                print("exception in new flow", ee)

            # ********************************** velocity statistical parameters **********************************

            try:
                velocity_time_kurtosis = kurtosis(np.array(velocityTWF))
            except:
                velocity_time_kurtosis = 0
            
            try:
                velocity_time_rms_org = getRMS(velocityTWF)

                if macID in ["70:B8:F6:02:49:34"]:
                    velocity_time_rms = round(velocity_time_rms_org, 2)
                else:
                    velocity_time_rms = StatFunctionsAdjustment(velocity_time_rms_org, 'velocity', axis, 'rms')

                """piezo sensor rms adjustments"""
                if macID == "CC:7B:5C:37:0B:40":
                    velocity_time_rms = velocity_time_rms - 0.6

                velocity_time_peak = getPeak(velocityTWF)
                velocity_time_peak_to_peak = getPeak_to_peak(velocityTWF)

            except:
                velocity_time_rms = 0
                velocity_time_peak = 0
                velocity_time_peak_to_peak = 0

            # Build axis-specific field names for VelocityStatTimeOptimized model
            dataVelocityStatTimeMasterUpdated = {
                "timestamp": local_dt,
                "composite": composite_key,
                "asset_id": asset_id,
                "mount_id": mount_id,
                f"rms_{axisOrientation}": velocity_time_rms,
                f"peak_{axisOrientation}": round(velocity_time_peak, 2),
                f"peak_to_peak_{axisOrientation}": round(velocity_time_peak_to_peak, 2),
                f"kurtosis_{axisOrientation}": round(velocity_time_kurtosis, 2)
            }

            dataVelocityStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(velocity_time_kurtosis,2),"rms":velocity_time_rms,"axis":axisOrientation,\
                                        "composite":composite_key,"asset_id":asset_id,"peak":round(velocity_time_peak,2),"peak_to_peak":round(velocity_time_peak_to_peak,2), 'mount_id':mount_id}

            try:
                obj, created = models.VelocityStatTimeOptimized.objects.update_or_create(
                    mount_id=mount_id,
                    timestamp=local_dt,
                    defaults=dataVelocityStatTimeMasterUpdated
                )
                vel_stat = True
                
            except Exception as ee:
                vel_stat = False
                print("exception in new flow", ee)




            # ********************************** displacement statistical parameters **********************************
            try:
                displacement_time_kurtosis = kurtosis(np.array(displacementTWF))
            except:
                displacement_time_kurtosis = 0

            try:
                displacement_time_rms_org = getRMS(displacementTWF)
                # displacement_time_rms = round(displacement_time_rms_org, 2)

                if macID in ["70:B8:F6:02:49:34"]:
                    displacement_time_rms = round(displacement_time_rms_org, 2)
                else:
                    displacement_time_rms = StatFunctionsAdjustment(displacement_time_rms_org, 'displacement', axis, 'rms')

                displacement_time_peak = getPeak(displacementTWF)
                displacement_time_peak_to_peak = getPeak_to_peak(displacementTWF)

            except:
                displacement_time_rms = 0
                displacement_time_peak = 0
                displacement_time_peak_to_peak = 0

            # Build axis-specific field names for DisplacementStatTimeOptimized model
            dataDisplacementStatTimeMasterUpdated = {
                "timestamp": local_dt,
                "composite": composite_key,
                "asset_id": asset_id,
                "mount_id": mount_id,
                f"rms_{axisOrientation}": displacement_time_rms,
                f"peak_{axisOrientation}": round(displacement_time_peak, 2),
                f"peak_to_peak_{axisOrientation}": round(displacement_time_peak_to_peak, 2),
                f"kurtosis_{axisOrientation}": round(displacement_time_kurtosis, 2)
            }

            # dataDisplacementStatTimeMaster = {'timestamp':local_dt,"kurtosis":round(displacement_time_kurtosis,2),"rms":displacement_time_rms,"axis":axisOrientation,\
            #                             "composite":composite_key,"asset_id":asset_id,"peak":round(displacement_time_peak,2),"peak_to_peak":round(displacement_time_peak_to_peak,2), 'mount_id':mount_id}

            try:
                obj, created = models.DisplacementStatTimeOptimized.objects.update_or_create(
                    mount_id=mount_id,
                    timestamp=local_dt,
                    defaults=dataDisplacementStatTimeMasterUpdated
                )
                dis_stat = True
                
            except Exception as ee:
                dis_stat = False
                print("exception in new flow", ee)



            # ********************************** EHNR Calculations **********************************
            try:
                ehnr = EHNR(np.array(vibrationData), samplingFrequency)
                ehnrData = {"composite": composite_key,"timestamp": local_dt,"ehnr": round(ehnr, 2),"axis": axisOrientation,"asset_id": asset_id, 'mount_id':mount_id}
                ehnrData_serializer = serializers.FrequencyDomainFeatuersSerializer(data=ehnrData)
                if ehnrData_serializer.is_valid():
                    ehnrData_serializer.save()
                else:
                    ehnr_err = get_error_msg(ehnrData_serializer.errors)
                    print("Error in ehnrData_serializer", ehnr_err)
            except Exception as e:
                print("exception in ehnr", e)
                pass



            # ********************************** Bearing Fault Frequencies **********************************

            try:
                bearingInstance = models.BearingDetailMaster.objects.get(mount_id=mount_id)
                bearingData = model_to_dict(bearingInstance)
            except:
                bearingData = {"bpfo": None,"bpfi": None,"bsf": None,"ftf": None}

            # ********************************** Acceleration Spectrum Bearing Fault Frequencies **********************************
            bff_data_acc = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation,  "signal_type": "Acceleration",  "asset_id":asset_id, "mount_id":mount_id }
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
                        except:
                            pass
                else:
                    bff_data_acc.update({falutFrequency+"_amp": [], falutFrequency+"_freq": []})

            # ********************************** Velocity Spectrum Bearing Fault Frequencies **********************************
            bff_data_vel = {"composite": composite_key, "timestamp": local_dt, "axis": axisOrientation,  "signal_type": "Velocity",  "asset_id":asset_id, 'mount_id':mount_id}
            for falutFrequency in ['bpfo','bpfi','bsf','ftf']:
                if bearingData.get(falutFrequency):
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

            # ********************************** Check current values against saved threshold values and update counter **********************************
            # composite + '-' + axis + '-' + signal_type + '-' + domain
            try:
                signalTypeList = ['acceleration', 'velocity', 'temp']
                for signal in signalTypeList:
                    # if signal == 'temp':
                        # #print("-----------------temp------------------",signal, tempData)
                    # comp_key = composite_key + '-' + axisOrientation + '-' + signal + '-time'
                    if signal in ['acceleration', 'velocity']:
                        threshold_data = get_threshold_data(mount_id, axisOrientation, signal, 'time')
                        threshold_counter_data = get_threshold_counter_data(mount_id, axisOrientation, signal, 'time')
                        if threshold_data != None and threshold_counter_data != None:
                            if signal == 'acceleration':
                                statfunctionList = ['rms', 'peak', 'peak_to_peak']
                                harmonicsList = ['one', 'two', 'three', 'four']
                                checkValuesAgainstThreshold(threshold_data, threshold_counter_data, dataAccelerationStatTimeMaster, statfunctionList, acceleration_harmonics_data if acceleration_harmonics_data else None, harmonicsList if acceleration_harmonics_data else None)
                            if signal == 'velocity':
                                statfunctionList = ['rms', 'peak', 'peak_to_peak']
                                harmonicsList = ['one', 'two', 'three', 'four']
                                checkValuesAgainstThreshold(threshold_data, threshold_counter_data, dataVelocityStatTimeMaster, statfunctionList, velocity_harmonics_data if velocity_harmonics_data else None, harmonicsList if velocity_harmonics_data else None)
                    if signal == 'temp' and axis == 'x':
                        threshold_data = get_threshold_data(mount_id, 'temp', signal, 'time')
                        threshold_counter_data = get_threshold_counter_data(mount_id, 'temp', signal, 'time')
                        if threshold_data != None and threshold_counter_data != None:
                            statfunctionList = ['temp']
                            checkValuesAgainstThreshold(threshold_data, threshold_counter_data, tempData, statfunctionList, None, None)

            except Exception as thresh_e:
                print("some exception in thresh_e",signal, thresh_e)

            bff_serializer = serializers.BearingFaultFrequenciesMasterSerializer(data = finalDataBFF, many=True)
            if bff_serializer.is_valid():
                bff_serializer.save()
                return "All Data Saved", composite_key, status.HTTP_201_CREATED
            return get_error_msg(bff_serializer.errors), status.HTTP_400_BAD_REQUEST
        else:
            return get_error_msg(RawSerializer.errors), status.HTTP_400_BAD_REQUEST
    except:
        return "Something went wrong.", status.HTTP_400_BAD_REQUEST


@shared_task(queue='defaultQueue')
def saveDataAcousticAsync(data, acousticData, fs):
    excitation_voltage = 3.3
    n = 12
    

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
         
        try:
            if fs <= 12000:
                high = 100
                low = 5000
                # show in trend
                df_filtered = bandPassFilter(df_processed, high, low, fs)  # save df_filtered for twf data on dashboard
                processed_rms_filtered = getRMS(df_filtered)
                rms_dB_filtered_raw = 20 * np.log10(processed_rms_filtered/ 2048)
                rms_dB_filtered = 132 - np.abs(rms_dB_filtered_raw)
            else:
                high = 10000
                if data.get("composite") == "ble_DC:1F:A4:41:18:A7_67138ad485b49a16b2dc738a_3766":
                    low = 75000
                else:
                    low = 39000
                df_filtered = bandPassFilter(df_processed, high, low, fs)  # save df_filtered for twf data on dashboard
                processed_rms_filtered = getRMS(df_filtered)
                rms_dB_filtered_raw = 20 * np.log10(processed_rms_filtered/ 2048)
                rms_dB_filtered = 132 - np.abs(rms_dB_filtered_raw)
        except Exception as ee:
            rms_dB_filtered = 0
            print("Exception in all raw data filter loop", ee)

        # //////////////////////////////////////// 0-10k hz filter ////////////////////////////////////////
        try:
            high_10k = 5
            low_10k = 10000
            df_filtered_10k = bandPassFilter(df_processed, high_10k, low_10k, fs)
            processed_rms_filtered_10k = getRMS(df_filtered_10k)
            rms_db_raw_10k = 20 * np.log10(processed_rms_filtered_10k/ 2048)
            rms_db_10k = 132 - np.abs(rms_db_raw_10k)

            fft_filtered_10k, f_10k = getFFT10K(df_filtered_10k, fs)

        except Exception as e:
            rms_db_10k = 0
            fft_filtered_10k = []
            f_10k = []
            print("Exception in 10k filter data", e)

        # //////////////////////////////////////// 20-40k hz filter ////////////////////////////////////////
        try:
            high_20k = 20000
            if data.get("composite") == "ble_DC:1F:A4:41:18:A7_67138ad485b49a16b2dc738a_3766":
                low_20k = 75000
            else:
                low_20k = 39000
            df_filtered_20k = bandPassFilter(df_processed, high_20k, low_20k, fs)
            processed_rms_filtered_20k = getRMS(df_filtered_20k)
            rms_db_raw_20k = 20 * np.log10(processed_rms_filtered_20k/ 2048)
            rms_db_20k = 132 - np.abs(rms_db_raw_20k)

            fft_filtered_20k, f_20k = getFFT20K(df_filtered_20k, fs, high_20k, low_20k)

        except Exception as e:
            rms_db_20k = 0
            fft_filtered_20k = []
            f_20k = []
            print("Exception in 20k filter data", e)

        try:
            acousticRMSData = {"composite": data.get("composite"), 'timestamp':data.get("timestamp"), \
                               'acoustic_db': round(rms_dB_filtered,2), 'acoustic_rms': round(rms_db,2), \
                               'acoustic_rms_10k': round(rms_db_10k,2), 'acoustic_rms_20k': round(rms_db_20k,2), \
                                'asset_id': data.get("asset_id"), 'flag': True}   # saving flag == True only of complete spectrum data (ble in this case not wired)
            acoustic_serializer = serializers.AcousticsMasterSerializer(data=acousticRMSData)
            if acoustic_serializer.is_valid():
                acoustic_serializer.save()
            else:
                return "Something went wrong while saving rms data loop 1{0}".format(get_error_msg(acoustic_serializer.errors)), status.HTTP_404_NOT_FOUND
        except Exception as e:
            return "Something went wrong while saving rms data loop 2{0}".format(e), status.HTTP_404_NOT_FOUND


        # try:
        #     high_stop_1 = 12200
        #     low_stop_1 = 13500
        #     df_filtered_cleared_1 = bandStopFilter(df_processed, high_stop_1, low_stop_1, fs, attenuation=10)

        #     high_stop_2 = 17000
        #     low_stop_2 = 19100
        #     df_filtered_cleared_2 = bandStopFilter(df_filtered_cleared_1, high_stop_2, low_stop_2, fs, attenuation=10)  # save df_filtered for spectrum data on dashboard

        #     high_stop_3 = 29900
        #     low_stop_3 = 31600
        #     df_filtered_cleared_3 = bandStopFilter(df_filtered_cleared_2, high_stop_3, low_stop_3, fs, attenuation=10)  # save df_filtered for spectrum data on dashboard

        #     high_stop_4 = 34200
        #     low_stop_4 = 35200
        #     df_filtered_cleared_4 = bandStopFilter(df_filtered_cleared_3, high_stop_4, low_stop_4, fs, attenuation=10)

        # except Exception as e:
        #     return "Something went wrong in filter of acoustic data {0}".format(e), status.HTTP_404_NOT_FOUND

        # try:
        #     df_fft, f = getFFT(df_processed, fs)
        #     # df_fft, f = getFFT(df_filtered_cleared_4, fs)

        #     acousticSpectrumData = {"composite": data.get("composite"), 'timestamp':data.get("timestamp"), \
        #                             'twf_data': np.round(df_filtered, 3), 'spectrum_data': np.round(df_fft, 3), 'frequency_data': np.round(f, 3), \
        #                             'spectrum_data_10k': np.round(fft_filtered_10k,3), 'spectrum_data_20k': np.round(fft_filtered_20k,3), \
        #                             'frequency_data_10k': np.round(f_10k,3), 'frequency_data_20k': np.round(f_20k, 3), \
        #                             'asset_id': data.get("asset_id"),'axis': data.get("axis")}
        #     acoustic_spectrum_serializer = serializers.AcousticsSpectrumMasterSerializer(data=acousticSpectrumData)
        #     if acoustic_spectrum_serializer.is_valid():
        #         acoustic_spectrum_serializer.save()
        #     else:
        #         return "Something went wrong while saving acoustic spectrum data {0}".format(get_error_msg(acoustic_spectrum_serializer.errors)), status.HTTP_404_NOT_FOUND

        # except Exception as e:
        #     return "Something went wrong in fft conversion of acoustic data {0}".format(e), status.HTTP_404_NOT_FOUND
        

        return "All Data Okay", status.HTTP_201_CREATED
    except Exception as e:
        return "Something went wrong in the main loop. {0}".format(e), status.HTTP_400_BAD_REQUEST


def saveFakeAcousticData(asset_id, composite_key):
    get_url = "https://cua119013p.oneabbott.com/api/device_raw_data/"
    headers = {'Content-Type': 'application/json'}
    axis = "a"
    timestamps1 = [1721321712,1721374313,1721378993,1721379554,1721380251,1721380432,1721398710,1721398822,1721401551,1721401732,1721402136,1721402317,1721402403,1721457784,1721458204,1721458504,1721458804,1721459331,1721459515,1721459703,1721460003,1721460303,1721460604,1721722440,1721722594,1721722897,1721724024,1721724324,1721725224,1721726124,1721727024,1721727924,1721728824,1721729724,1721731524,1721735226,1721735715,1721736060,1721736254,1721736601,1721736763,1721737090,1721742997,1721743269]

    payload = json.dumps({
        "composite": "ble_EB:32:7A:32:41:08_6638b7a126336f730b4837ba_2957",
        "axis": axis,
        "timestamp": random.choice(timestamps1),
        "data_type": "raw"
    })
    try:
        response = requests.request("POST", get_url, headers=headers, data=payload)
        response_dataaa = response.json()
        response_data = response_dataaa.get("data")
        fs = response_data.get("sampling_rate")
        response_data.update({'asset_id':asset_id, "composite": composite_key, "axis": "a"})
        # print("get response", response_data)

        # pdb.set_trace()
        try:
            utc_dt = datetime.datetime.utcfromtimestamp(response_data.get("timestamp")).replace(tzinfo=pytz.utc)
            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
        except:
            return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
        response_data.update({'timestamp':local_dt})
        
        
        excitation_voltage = 3.3
        n = 12
        high = 10000
        low = 40000


        try:
            df = np.array(response_data.get("raw_data")[20:])

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

            # //////////////////////////////////////// 0-10k hz filter ////////////////////////////////////////
            try:
                high_10k = 5
                low_10k = 10000
                df_filtered_10k = bandPassFilter(df_processed, high_10k, low_10k, fs)
                processed_rms_filtered_10k = getRMS(df_filtered_10k)
                rms_db_raw_10k = 20 * np.log10(processed_rms_filtered_10k/ 2048)
                rms_db_10k = 132 - np.abs(rms_db_raw_10k)

                fft_filtered_10k, f_10k = getFFT10K(df_filtered_10k, fs)

            except Exception as e:
                fft_filtered_10k = []
                f_10k = []
                print("Exception in 10k filter data", e)

            # //////////////////////////////////////// 20-40k hz filter ////////////////////////////////////////
            try:
                high_20k = 20000
                low_20k = 40000
                df_filtered_20k = bandPassFilter(df_processed, high_20k, low_20k, fs)
                processed_rms_filtered_20k = getRMS(df_filtered_20k)
                rms_db_raw_20k = 20 * np.log10(processed_rms_filtered_20k/ 2048)
                rms_db_20k = 132 - np.abs(rms_db_raw_20k)

                fft_filtered_20k, f_20k = getFFT20K(df_filtered_20k, fs, high_20k, low_20k)

            except Exception as e:
                fft_filtered_20k = []
                f_20k = []
                print("Exception in 20k filter data", e)

            try:
                acousticRMSData = {"composite": response_data.get("composite"), 'timestamp':response_data.get("timestamp"), \
                                'acoustic_db': round(rms_dB_filtered_raw,2), 'acoustic_rms': round(rms_db,2), \
                                'acoustic_rms_10k': round(rms_db_10k,2), 'acoustic_rms_20k': round(rms_db_20k,2), \
                                    'asset_id': response_data.get("asset_id"), 'flag': True}   # saving flag == True only of complete spectrum data (ble in this case not wired)
                acoustic_serializer = serializers.AcousticsMasterSerializer(data=acousticRMSData)
                if acoustic_serializer.is_valid():
                    acoustic_serializer.save()
                else:
                    print("-------------------", get_error_msg(acoustic_serializer.errors))
                    return "Something went wrong while saving rms data {0}".format(get_error_msg(acoustic_serializer.errors)), status.HTTP_404_NOT_FOUND
            except Exception as e:
                return "Something went wrong while saving rms data {0}".format(e), status.HTTP_404_NOT_FOUND


            # try:
            #     high_stop_1 = 12200
            #     low_stop_1 = 13500
            #     df_filtered_cleared_1 = bandStopFilter(df_processed, high_stop_1, low_stop_1, fs, attenuation=10)

            #     high_stop_2 = 17000
            #     low_stop_2 = 19100
            #     df_filtered_cleared_2 = bandStopFilter(df_filtered_cleared_1, high_stop_2, low_stop_2, fs, attenuation=10)  # save df_filtered for spectrum data on dashboard

            #     high_stop_3 = 29900
            #     low_stop_3 = 31600
            #     df_filtered_cleared_3 = bandStopFilter(df_filtered_cleared_2, high_stop_3, low_stop_3, fs, attenuation=10)  # save df_filtered for spectrum data on dashboard

            #     high_stop_4 = 34200
            #     low_stop_4 = 35200
            #     df_filtered_cleared_4 = bandStopFilter(df_filtered_cleared_3, high_stop_4, low_stop_4, fs, attenuation=10)

            # except Exception as e:
            #     return "Something went wrong in filter of acoustic data {0}".format(e), status.HTTP_404_NOT_FOUND

            # try:
            #     df_fft, f = getFFT(df_processed, fs)
            #     # df_fft, f = getFFT(df_filtered_cleared_4, fs)

            #     acousticSpectrumData = {"composite": response_data.get("composite"), 'timestamp':response_data.get("timestamp"), \
            #                             'twf_data': np.round(df_filtered, 3), 'spectrum_data': np.round(df_fft, 3), 'frequency_data': np.round(f, 3), \
            #                             'spectrum_data_10k': np.round(fft_filtered_10k,3), 'spectrum_data_20k': np.round(fft_filtered_20k,3), \
            #                             'frequency_data_10k': np.round(f_10k,3), 'frequency_data_20k': np.round(f_20k, 3), \
            #                             'asset_id': response_data.get("asset_id"),'axis': response_data.get("axis")}
            #     acoustic_spectrum_serializer = serializers.AcousticsSpectrumMasterSerializer(data=acousticSpectrumData)
            #     if acoustic_spectrum_serializer.is_valid():
            #         acoustic_spectrum_serializer.save()
            #     else:
            #         return "Something went wrong while saving acoustic spectrum data {0}".format(get_error_msg(acoustic_spectrum_serializer.errors)), status.HTTP_404_NOT_FOUND

            # except Exception as e:
            #     return "Something went wrong in fft conversion of acoustic data {0}".format(e), status.HTTP_404_NOT_FOUND
            
            print("----------------------------------All Data Okay")



            return "All Data Okay", status.HTTP_201_CREATED
        except Exception as e:
            return "Something went wrong. {0}".format(e), status.HTTP_400_BAD_REQUEST
        


    except Exception as ee:
        print("excepteeeeeeeeeee", ee)



@shared_task(queue='defaultQueue')
def saveMagneticDataAsync(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp):
    print("saving magnetic data")
    try:
        RawSerializer = serializers.RawDataMasterSerializer(data=data)
        if RawSerializer.is_valid():
            RawSerializer.save()
        else:
            return get_error_msg(RawSerializer.errors), status.HTTP_400_BAD_REQUEST
        try:
            rData = rData - np.mean(rData)
            high = 5
            low = 75
            df_filtered = bandPassFilter(rData, high, low, samplingFrequency)  # save df_filtered for twf data on dashboard
            processed_rms_filtered = getRMS(df_filtered)
            fft_filtered, f = getFFT(df_filtered, samplingFrequency)
            try:
                MagneticSpectrumData = {"composite": composite_key, 'timestamp':data.get("timestamp"), \
                                        'twf_data': np.round(df_filtered, 3), 'spectrum_data': np.round(fft_filtered, 3), 'frequency_data': np.round(f, 3), \
                                        'asset_id': asset_id,'axis': data.get("axis")}
                magnetic_spectrum_serializer = serializers.MagneticFluxSpectrumMasterSerializer(data=MagneticSpectrumData)

                magnetic_stat_data = {"composite": composite_key, 'timestamp':data.get("timestamp"), 'rms': processed_rms_filtered, 'asset_id': asset_id,'axis': data.get("axis")}
                magnetic_stat_data_serializer = serializers.MagneticFluxStatMasterSerializer(data=magnetic_stat_data)
                if magnetic_spectrum_serializer.is_valid():
                    if magnetic_stat_data_serializer.is_valid():
                        magnetic_stat_data_serializer.save()
                        magnetic_spectrum_serializer.save()
                        return "All Data Saved", status.HTTP_201_CREATED
                    return "Something went wrong while saving acoustic spectrum data {0}".format(get_error_msg(magnetic_spectrum_serializer.errors)), status.HTTP_404_NOT_FOUND
                else:
                    return "Something went wrong while saving acoustic spectrum data {0}".format(get_error_msg(magnetic_spectrum_serializer.errors)), status.HTTP_404_NOT_FOUND
            except Exception as e:
                return "Something went wrong in fft conversion of acoustic data {0}".format(e), status.HTTP_404_NOT_FOUND
        except Exception as e:
            return "Something went wrong. {0}".format(e), status.HTTP_400_BAD_REQUEST
    except:
        return "Something went wrong.", status.HTTP_400_BAD_REQUEST


# @shared_task 
# def sendMailSingle(alarmHistoryData):
#     print(" ---------------- here in sending mail function ---------------- ", alarmHistoryData)
#     return True




@shared_task(queue='mailQueue')
def sendMailSingle(alarmHistoryData):
    #print(" ---------------- here in sending mail function ---k------------- ", alarmHistoryData)
    #print("asset id", alarmHistoryData.get("asset_id"))
    url = "https://cua119013p.oneabbott.com/cmms_api/api/asset_master/get_user_against_asset?asset_id=" +  alarmHistoryData.get("asset_id")
    email_sent = False
    try:
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()  # Raises HTTPError for bad status codes
        res = response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request failed for asset {alarmHistoryData.get('asset_id')}: {str(e)}")
        return False
    except json.JSONDecodeError as e:
        print(f"Invalid JSON response for asset {alarmHistoryData.get('asset_id')}: {str(e)}")
        return False
    if res.get("message") == 'success':
        # apiData = res.json().get("data")
        apiData = res.get("data")
        asset_name = apiData.get("asset_name")
        location_name = apiData.get("location_name")
        top_asset_name = apiData.get("top_asset_name")
        # recipient_mail = apiData.get("email_list")
        users = apiData.get("users")
        # redirect_url = apiData.get("redirect_url")
        for single_user in users:
            try:
                country_code = timezone_list.get(single_user.get("contact_number").get("phone_no").get("countryCode"))
                country_tz = pytz.timezone(country_code)
            except:
                country_code = timezone_list.get("IN")
                country_tz = pytz.timezone(country_code)
 
            dt_country = alarmHistoryData.get("timestamp").astimezone(country_tz)
 
            start, end = createRandom(4)
            # url = "http://localhost:4200/redirect?key="                         # local url
            url = "https://cua119013p.oneabbott.com/pdm/redirect?key="
 
 
            if alarmHistoryData.get("trend_type") in ['rms_amp', 'peak_amp', 'peak_to_peak_amp', 'kurtosis_amp']:
                component = 'assets/asset-analyze'
                assetId = alarmHistoryData.get("asset_id")
                endPoint = alarmHistoryData.get("composite").split("_")[-1]
                tabType = 'vibration'
                trendDomain = 'time-domain'
                signalType = alarmHistoryData.get("signal_type")
                trendType = alarmHistoryData.get("trend_type").split("_amp")[0]
                selectedAxis = alarmHistoryData.get("axis")
                redirectURL = component+'/'+assetId+'/'+endPoint+'/'+tabType+'/'+trendDomain+'/'+signalType+'/'+trendType+'/'+selectedAxis
 
            elif alarmHistoryData.get("trend_type") in ['one_amp', 'two_amp', 'three_amp', 'four_amp']:
                component = 'assets/asset-analyze'
                assetId = alarmHistoryData.get("asset_id")
                endPoint = alarmHistoryData.get("composite").split("_")[-1]
                tabType = 'vibration'
                trendDomain = 'freq-domain'
                signalType = alarmHistoryData.get("signal_type")
                trendType = alarmHistoryData.get("trend_type").split("_amp")[0]
                selectedAxis = alarmHistoryData.get("axis")
                redirectURL = finalUrl = component+'/'+assetId+'/'+endPoint+'/'+tabType+'/'+trendDomain+'/harmonics'
 
            elif alarmHistoryData.get("trend_type") == 'temp_amp':
                component = 'assets/asset-analyze'
                assetId = alarmHistoryData.get("asset_id")
                endPoint = alarmHistoryData.get("composite").split("_")[-1]
                tabType = 'temperature'
                trendDomain = 'temperature'
                signalType = 'temperature'
                trendType = 'temperature'
                selectedAxis = 'temperature'
                redirectURL = finalUrl = component+'/'+assetId+'/'+endPoint+'/'+tabType
 
            else:
                component = 'assets/asset-health'
                assetId = alarmHistoryData.get("asset_id")
                endPoint = alarmHistoryData.get("composite").split("_")[-1]
                tabType = 'health'
                trendDomain = 'fault'
                signalType = 'fault'
                trendType = 'fault'
                selectedAxis = 'fault'
                redirectURL = component+'/'+assetId+'/'+tabType+'/'+endPoint
 
            user_data = json.dumps({
                "token": single_user.get("token"),
                "id": single_user.get("id"),
                "redirect_url": redirectURL
                })
            encoded_data = base64.b64encode(user_data.encode('utf-8'))
            redirect_url = url + start + encoded_data.decode('utf-8') + end
 
            if alarmHistoryData.get("signal_type") == 'temp':
                final_data = {
                    "location": alarmHistoryData.get("sensor_location"), "date": dt_country.strftime("%b. %d, %Y, %I:%M:%S %p"),
                    "signal_type": 'Temperature', "trend_type":  'Temperature', "axis": '-',
                    "set_threshold": alarmHistoryData.get("threshold_value"), "observed_value": alarmHistoryData.get("observed_value"), "asset_name": asset_name,
                    "location_name": location_name, "top_asset_name": top_asset_name, "redirect_url": redirect_url
                }
            else:
                final_data = {
                    "location": alarmHistoryData.get("sensor_location"), "date": dt_country.strftime("%b. %d, %Y, %I:%M:%S %p"),
                    "signal_type": alarmHistoryData.get("signal_type").capitalize(), "trend_type":  ' '.join(alarmHistoryData.get("trend_type").split('_')[:-1]).capitalize(), "axis": alarmHistoryData.get("axis").capitalize(),
                    "set_threshold": alarmHistoryData.get("threshold_value"), "observed_value": alarmHistoryData.get("observed_value"), "asset_name": asset_name,
                    "location_name": location_name, "top_asset_name": top_asset_name, "redirect_url": redirect_url
                }
            
            # Define priority-specific text mappings
            priority_config = {
                "Critical": {
                    "header": "CRITICAL ALERT",
                    "intro": "An anomaly of Critical level has been detected"
                },
                "Danger": {
                    "header": "DANGER ALERT",
                    "intro": "An anomaly of Danger level has been detected"
                },
                "Alert": {
                    "header": "ALERT NOTIFICATION",
                    "intro": "An anomaly of Alert level has been detected"
                }
            }
            
            # Get priority configuration
            priority = alarmHistoryData.get("priority")
            config = priority_config.get(priority, priority_config["Alert"])  # Default to Alert if priority not found
            
            # Create single plain text message with dynamic content
            plain_text_message = f"""Hi Team,
 
            {config["intro"]} in the {final_data.get("asset_name")} asset. Please find the details below:
 
            {config["header"]}
 
            Details:
            Location Name: {final_data.get("location_name")}
            Equipment Name: {final_data.get("top_asset_name")}
            Asset Name: {final_data.get("asset_name")}
            Fault Location: {final_data.get("location")}
            Last Collection Date: {final_data.get("date")}
            Signal Type: {final_data.get("signal_type")}
            Parameter Type: {final_data.get("trend_type")}
            Axis: {final_data.get("axis")}
            Set Threshold Value: {final_data.get("set_threshold")}
            Observed Value: {final_data.get("observed_value")}
 
            To review more details, please log in to the system: {final_data.get("redirect_url")}
 
            —
            Team Presage Insights"""
 
            mail_sending_time = datetime.datetime.now(pytz.UTC).astimezone(country_tz).strftime("%m-%d-%Y, %I:%M:%S %p")
            subject = 'Sensor Alerts: '+'   '+final_data.get("location")+' > '+final_data.get("asset_name")+' ('+str(mail_sending_time)+' )'
            email_from = "Sensor-Alerts<no-reply@abbott.com>"
            recipient_list = [single_user.get("email")]
            #recipient_list = ["pulkit.sharma@abbott.com"]
            try:
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=plain_text_message,  # Use plain text message as body
                    from_email=email_from,
                    to=recipient_list,
                    reply_to=['no-reply@abbott.com']
                )
 
                # Remove HTML-related configurations since we're using plain text
                # email.attach_alternative(html_message, "text/html")
                # email.content_subtype = 'html'
                # email.mixed_subtype = 'related'
                
                res = email.send(fail_silently=False)
                if res:  # res is 1 if email sent successfully, 0 otherwise
                    email_sent = True
                # print("mail sent to", single_user.get("email"))
            except Exception as e:
                print(f"--------------------------mail not sent to {single_user.get('email')}: {str(e)}--------------------------")
    else:
        print("some error occured while getting user_against_asset_api", res, " asset_id= ", alarmHistoryData.get("asset_id"))
 
    return email_sent
 




# @shared_task 
# def saveRMSData(df, sensor_type):
        
#         macId = sensor_type + '_' + df.get("mac")
#         sensorType = sensor_type
#         # timestamp = df.get("timestamp", None)
#         timestamp = round(datetime.datetime.now().timestamp())   # using timestamp from local ec2 instead of sensor's
#         aRMSx = df.get("aRMSx", None)
#         aRMSy = df.get("aRMSy", None)
#         aRMSz = df.get("aRMSz", None)
#         vRMSx = df.get("vRMSx", None)
#         vRMSy = df.get("vRMSy", None)
#         vRMSz = df.get("vRMSz", None)
#         aP2Px = df.get("aP2Px", None)
#         aP2Py = df.get("aP2Py", None)
#         aP2Pz = df.get("aP2Pz", None)
        
#         temperature = df.get("temperature")
#         if df.get("mac") in ['E4:65:B8:2D:5A:A4', 'E4:65:B8:2B:34:0C']:
#             acoustic_db = df.get("aucaustic", 0)-4
#         else:
#             acoustic_db = df.get("aucaustic", 0)
#         acoustic_rms = df.get("aucausticRMS")
#         tempFlag = False
#         acousticFlag = False
#         accelerationFlag = False
#         velocityFlag = False


#         utc_dt = datetime.datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.utc)
#         local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))

#         try:
#             # pdb.set_trace()

#             ########################## function is only for wired version to save edge RMS values ##########################
#             try:
#                 device_data = get_mount_data(macId)
#                 # device_data = models.DeviceMountMaster.objects.get(mac_id=macId, is_linked=True)
#                 asset_id = device_data.get('asset_id')
#                 composite_key = device_data.get('composite_id')
#                 mount_id = device_data.get('id')
#                 sensorOrientation = device_data.get('mount_direction')

#                 axisInfo = get_sensor_orientation_data_rms_only(sensorType, sensorOrientation)
#                 # sesnorOrientData = models.SensorPositionMaster.objects.get(sensor_type=sensorType)
#                 # axisInfo = sesnorOrientData.orientation.get(sensorOrientation)
#             except Exception as e:
#                 # print("unmapped sensor ", e, macId)
#                 res = {"result": False, "message": "Unable to fetech device. Contact admin...", "mac_id": macId}
#                 return res
            
#             dataAccelerationStatTimeMaster = [
#                 models.AccelerationStatTimeMaster(timestamp = local_dt, rms = aRMSx, peak_to_peak = aP2Px, axis = axisInfo.get("x"), composite = composite_key, asset_id = asset_id, rms_only = True),
#                 models.AccelerationStatTimeMaster(timestamp = local_dt, rms = aRMSy, peak_to_peak = aP2Py, axis = axisInfo.get("y"), composite = composite_key, asset_id = asset_id, rms_only = True),
#                 models.AccelerationStatTimeMaster(timestamp = local_dt, rms = aRMSz, peak_to_peak = aP2Pz, axis = axisInfo.get("z"), composite = composite_key, asset_id = asset_id, rms_only = True)
#             ]

#             dataVelocityStatTimeMaster = [
#                 models.VelocityStatTimeMaster(timestamp = local_dt, rms = vRMSx, axis = axisInfo.get("x"), composite = composite_key, asset_id = asset_id, rms_only = True),
#                 models.VelocityStatTimeMaster(timestamp = local_dt, rms = vRMSy, axis = axisInfo.get("y"), composite = composite_key, asset_id = asset_id, rms_only = True),
#                 models.VelocityStatTimeMaster(timestamp = local_dt, rms = vRMSz, axis = axisInfo.get("z"), composite = composite_key, asset_id = asset_id, rms_only = True)
#             ]

#             try:
#                 dataTemperatureMaster = {"composite": composite_key, 'timestamp':local_dt, 'temp': round(temperature,2),'asset_id': asset_id}
#                 temp_serializer = serializers.TemperatureMasterSerializer(data=dataTemperatureMaster)
#                 if temp_serializer.is_valid():
#                     temp_serializer.save()
#                     tempFlag = True
#                 else:
#                     res = {"result": False, "message": "Something wrong with temperature serializer.", "mac_id": macId}
#             except:
#                 res = {"result": False, "message": "Something went wrong in temperature loop.", "mac_id": macId}

            
#             try:
#                 dataAcousticMaster = {"composite": composite_key, 'timestamp':local_dt, 'acoustic_db': round(acoustic_db,2), 'acoustic_rms': round(acoustic_rms,2), 'asset_id': asset_id}
#                 acoustic_serializer = serializers.AcousticsMasterSerializer(data=dataAcousticMaster)
#                 if acoustic_serializer.is_valid():
#                     acoustic_serializer.save()
#                     acousticFlag = True
#                 else:
#                     res = {"result": False, "message": "Something wrong with acoustic serializer.", "mac_id": macId}
#             except:
#                 res = {"result": False, "message": "Something went wrong in acoustic loop.", "mac_id": macId}

            
            
#             try:
#                 accModel = models.AccelerationStatTimeMaster.objects.bulk_create(dataAccelerationStatTimeMaster)
#                 accelerationFlag = True
#             except:
#                 res = {"result": False, "message": "Something wrong with acceleration serializer.", "mac_id": macId}
            
#             try:
#                 velModel = models.VelocityStatTimeMaster.objects.bulk_create(dataVelocityStatTimeMaster)
#                 velocityFlag = True
#             except:
#                 res = {"result": False, "message": "Something wrong with velocity serializer.", "mac_id": macId}

#             if tempFlag and accelerationFlag and velocityFlag:


#                 # ********************************** Check current values against saved threshold values and update counter **********************************
#                 # composite + '-' + axis + '-' + signal_type + '-' + domain
#                 """-------------------------- checking for acceleration -------------------------- """
#                 try:
#                     statfunctionList = ['rms', 'peak_to_peak']
#                     for i in dataAccelerationStatTimeMaster:
#                         threshold_data = get_threshold_data(i.composite, i.axis, 'acceleration', 'time')
#                         threshold_counter_data = get_threshold_counter_data(i.composite, i.axis, 'acceleration', 'time')
#                         acceleration_data = {'timestamp':i.timestamp,"rms":i.rms,"axis":i.axis, "composite":i.composite,"asset_id":i.asset_id,"peak_to_peak":i.peak_to_peak}
#                         checkValuesAgainstThreshold(threshold_data, threshold_counter_data, acceleration_data, statfunctionList, None, None)
#                 except Exception as thresh_e:
#                     # print("exception", thresh_e)
#                     pass

#                 """-------------------------- checking for velocity -------------------------- """
#                 try:
#                     statfunctionList = ['rms']
#                     for i in dataVelocityStatTimeMaster:
#                         threshold_data = get_threshold_data(i.composite, i.axis, 'velocity', 'time')
#                         threshold_counter_data = get_threshold_counter_data(i.composite, i.axis, 'velocity', 'time')
#                         velocity_data = {'timestamp':i.timestamp,"rms":i.rms,"axis":i.axis, "composite":i.composite,"asset_id":i.asset_id,"peak_to_peak":i.peak_to_peak}
#                         checkValuesAgainstThreshold(threshold_data, threshold_counter_data, velocity_data, statfunctionList, None, None)
#                 except Exception as thresh_e:
#                     # print("exception", thresh_e)
#                     pass


#                 """-------------------------- checking for temperature -------------------------- """
#                 try:
#                     if dataTemperatureMaster:
#                         statfunctionList = ['temp']
#                         threshold_data = get_threshold_data(dataTemperatureMaster.get("composite"), 'temp', 'temp', 'time')
#                         threshold_counter_data = get_threshold_counter_data(dataTemperatureMaster.get("composite"), 'temp', 'temp', 'time')
#                         checkValuesAgainstThreshold(threshold_data, threshold_counter_data, dataTemperatureMaster, statfunctionList, None, None)
#                 except Exception as thresh_e:
#                     print("some exception in thresh_e", thresh_e)



#                 res = {"result": True, "message": "All data saved.", "mac_id": macId}
#                 return res
#             else:
#                 return res
#         except:
#             # return Response({"message": "Something went wrong, kindly contact admin."}, status = status.HTTP_400_BAD_REQUEST)
#             res = {"result": False, "message": "Something went wrong in {0} rms data.".format(sensor_type), "mac_id": macId}
#             return res
        



@shared_task(queue='wiredRmsQueue') 
def saveRMSData(df, sensor_type):
        
    macId = sensor_type + '_' + df.get("mac")
    sensorType = sensor_type
    timestamp = df.get("timestamp", None)
    aRMSx = df.get("aRMSx", None)
    aRMSy = df.get("aRMSy", None)
    aRMSz = df.get("aRMSz", None)
    vRMSx = df.get("vRMSx", None)
    vRMSy = df.get("vRMSy", None)
    vRMSz = df.get("vRMSz", None)
    aP2Px = df.get("aP2Px", None)
    aP2Py = df.get("aP2Py", None)
    aP2Pz = df.get("aP2Pz", None)

    values = [aRMSx, aRMSy, aRMSz, vRMSx, vRMSy, vRMSz, aP2Px, aP2Py, aP2Pz]
    if all(v is None or (isinstance(v, (int, float)) and v < 100) for v in values):

       
        temperature = df.get("temperature")
        if df.get("mac") in ['E4:65:B8:2D:5A:A4', 'E4:65:B8:2B:34:0C']:
            acoustic_db = df.get("aucaustic", 0)-4
        else:
            acoustic_db = df.get("aucaustic", 0)
        acoustic_rms = df.get("aucausticRMS", 0)
        
        if not 0 <= acoustic_db <= 100:
            acoustic_db = 0
        if not 0 <= acoustic_rms <= 100:
            acoustic_rms = 0


        tempFlag = False
        acousticFlag = False
        accelerationFlag = False
        velocityFlag = False


        utc_dt = datetime.datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.utc)
        local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))

        try:
            # pdb.set_trace()

            ########################## function is only for wired version to save edge RMS values ##########################
            try:
                device_data = get_mount_data(macId)
                # device_data = models.DeviceMountMaster.objects.get(mac_id=macId, is_linked=True)
                asset_id = device_data.get('asset_id')
                composite_key = device_data.get('composite_id')
                mount_id = device_data.get('id')
                sensorOrientation = device_data.get('mount_direction')

                axisInfo = get_sensor_orientation_data_rms_only(sensorType, sensorOrientation)
                # sesnorOrientData = models.SensorPositionMaster.objects.get(sensor_type=sensorType)
                # axisInfo = sesnorOrientData.orientation.get(sensorOrientation)
            except Exception as e:
                # print("unmapped sensor ", e, macId)
                res = {"result": False, "message": "Unable to fetech device. Contact admin...", "mac_id": macId}
                return res

            # ************************************ saving data for acceleration stats   ************************************

            dataAccelerationStatTimeMasterUpdated = {}

            rms_key_x = "rms_" + axisInfo.get("x")
            rms_key_y = "rms_" + axisInfo.get("y")
            rms_key_z = "rms_" + axisInfo.get("z")

            peak_to_peak_key_x = "peak_to_peak_" + axisInfo.get("x")
            peak_to_peak_key_y = "peak_to_peak_" + axisInfo.get("y")
            peak_to_peak_key_z = "peak_to_peak_" + axisInfo.get("z")

            dataAccelerationStatTimeMasterUpdated[rms_key_x] = aRMSx
            dataAccelerationStatTimeMasterUpdated[rms_key_y] = aRMSy
            dataAccelerationStatTimeMasterUpdated[rms_key_z] = aRMSz

            dataAccelerationStatTimeMasterUpdated[peak_to_peak_key_x] = aP2Px
            dataAccelerationStatTimeMasterUpdated[peak_to_peak_key_y] = aP2Py
            dataAccelerationStatTimeMasterUpdated[peak_to_peak_key_z] = aP2Pz

            dataAccelerationStatTimeMaster = [
                {"timestamp": local_dt, "rms": aRMSx, "peak_to_peak": aP2Px, "axis": axisInfo.get("x"), "composite": composite_key, "asset_id": asset_id, "rms_only": True, "mount_id": mount_id},
                {"timestamp": local_dt, "rms": aRMSy, "peak_to_peak": aP2Py, "axis": axisInfo.get("y"), "composite": composite_key, "asset_id": asset_id, "rms_only": True, "mount_id": mount_id},
                {"timestamp": local_dt, "rms": aRMSz, "peak_to_peak": aP2Pz, "axis": axisInfo.get("z"), "composite": composite_key, "asset_id": asset_id, "rms_only": True, "mount_id": mount_id}
            ]

            # ************************************ saving data for velocity stats   ************************************

            dataVelocityStatTimeMasterUpdated = {}

            rms_key_x = "rms_" + axisInfo.get("x")
            rms_key_y = "rms_" + axisInfo.get("y")
            rms_key_z = "rms_" + axisInfo.get("z")

            dataVelocityStatTimeMasterUpdated[rms_key_x] = vRMSx
            dataVelocityStatTimeMasterUpdated[rms_key_y] = vRMSy
            dataVelocityStatTimeMasterUpdated[rms_key_z] = vRMSz

            dataVelocityStatTimeMaster = [
                {"timestamp": local_dt, "rms": vRMSx, "axis": axisInfo.get("x"), "composite": composite_key, "asset_id": asset_id, "rms_only": True, "mount_id": mount_id},
                {"timestamp": local_dt, "rms": vRMSy, "axis": axisInfo.get("y"), "composite": composite_key, "asset_id": asset_id, "rms_only": True, "mount_id": mount_id},
                {"timestamp": local_dt, "rms": vRMSz, "axis": axisInfo.get("z"), "composite": composite_key, "asset_id": asset_id, "rms_only": True, "mount_id": mount_id}
            ]

            dataTemperatureMaster = {"composite": composite_key, 'timestamp':local_dt, 'temp': round(temperature,2) if temperature is not None else None,'asset_id': asset_id, 'mount_id': mount_id}


            # dataAcousticMaster = {"composite": composite_key, 'timestamp':local_dt, 'acoustic_db': round(acoustic_db,2) if acoustic_db is not None else None, 'acoustic_rms': round(acoustic_rms,2) if acoustic_rms is not None else None, 'asset_id': asset_id, 'mount_id': mount_id}


            # --- START: Redis Caching Logic ---
            redis_packet_for_validation = {
                "composite_key": composite_key,
                "a_rms_Axial": dataAccelerationStatTimeMasterUpdated.get("rms_Axial"),
                "a_rms_Vertical": dataAccelerationStatTimeMasterUpdated.get("rms_Vertical"),
                "a_rms_Horizontal": dataAccelerationStatTimeMasterUpdated.get("rms_Horizontal"),
                "a_p2p_Axial": dataAccelerationStatTimeMasterUpdated.get("peak_to_peak_Axial"),
                "a_p2p_Vertical": dataAccelerationStatTimeMasterUpdated.get("peak_to_peak_Vertical"),
                "a_p2p_Horizontal": dataAccelerationStatTimeMasterUpdated.get("peak_to_peak_Horizontal"),
                "v_rms_Axial": dataVelocityStatTimeMasterUpdated.get("rms_Axial"),
                "v_rms_Vertical": dataVelocityStatTimeMasterUpdated.get("rms_Vertical"),
                "v_rms_Horizontal": dataVelocityStatTimeMasterUpdated.get("rms_Horizontal"),
                "temperature": temperature,
                "acoustic_db": acoustic_db,
                "acoustic_rms": acoustic_rms,
            }

            # 2. Validate the prepared packet.
            if not validate_sensor_data_packet_wired(redis_packet_for_validation):
                return {"result": False, "message": "Invalid or incomplete data packet, dropped.", "mac_id": macId}

            # 3. Create the final packet for Redis with all necessary info.
            redis_packet = {
                "composite_key": composite_key,
                "mount_id": str(mount_id),
                "asset_id": str(asset_id),
                "local_dt_iso": local_dt.isoformat(),
                **redis_packet_for_validation 
            }

            # 4. Write the validated packet to Redis.
            try:
                redis_key = f"rms_batch:{composite_key}:{timestamp}"
                redis_client_rms_batch.set(redis_key, json.dumps(redis_packet))
            except Exception as e:
                # If Redis fails, we cannot proceed.
                return {"result": False, "message": "Failed to write to Redis cache", "error": str(e), "mac_id": macId}


            # ********************************** Check current values against saved threshold values and update counter ***********************************
            # composite + '-' + axis + '-' + signal_type + '-' + domain
            """-------------------------- checking for acceleration -------------------------- """
            try:
                statfunctionList = ['rms', 'peak_to_peak']
                for i in dataAccelerationStatTimeMaster:
                    threshold_data = get_threshold_data(i.get("mount_id"), i.get("axis"), 'acceleration', 'time')
                    threshold_counter_data = get_threshold_counter_data(i.get("mount_id"), i.get("axis"), 'acceleration', 'time')
                    acceleration_data = {'timestamp':i.get("timestamp"),"rms":i.get("rms"),"axis":i.get("axis"), "composite":i.get("composite"),"asset_id":i.get("asset_id"),"peak_to_peak":i.get("peak_to_peak")}
                    checkValuesAgainstThreshold(threshold_data, threshold_counter_data, acceleration_data, statfunctionList, None, None)
            except Exception as thresh_e:
                # #print("exception", thresh_e)
                pass

            """-------------------------- checking for velocity -------------------------- """
            try:
                statfunctionList = ['rms']
                for i in dataVelocityStatTimeMaster:
                    threshold_data = get_threshold_data(i.get("mount_id"), i.get("axis"), 'velocity', 'time')
                    threshold_counter_data = get_threshold_counter_data(i.get("mount_id"), i.get("axis"), 'velocity', 'time')
                    velocity_data = {'timestamp':i.get("timestamp"),"rms":i.get("rms"),"axis":i.get("axis"), "composite":i.get("composite"),"asset_id":i.get("asset_id"),"peak_to_peak":i.get("peak_to_peak")}
                    checkValuesAgainstThreshold(threshold_data, threshold_counter_data, velocity_data, statfunctionList, None, None)
            except Exception as thresh_e:
                # #print("exception", thresh_e)
                pass


            """-------------------------- checking for temperature -------------------------- """
            try:
                if dataTemperatureMaster:
                    statfunctionList = ['temp']
                    threshold_data = get_threshold_data(dataTemperatureMaster.get("mount_id"), 'temp', 'temp', 'time')
                    threshold_counter_data = get_threshold_counter_data(dataTemperatureMaster.get("mount_id"), 'temp', 'temp', 'time')
                    checkValuesAgainstThreshold(threshold_data, threshold_counter_data, dataTemperatureMaster, statfunctionList, None, None)
            except Exception as thresh_e:
                print("some exception in thresh_e", thresh_e)



            res = {"result": True, "message": "Data validated and cached for batch processing.", "mac_id": macId}
            return res
        except Exception as e:
            print("------------------------e-------------------------------", e)
            # return Response({"message": "Something went wrong, kindly contact admin."}, status = status.HTTP_400_BAD_REQUEST)
            res = {"result": False, "message": "Something went wrong in {0} rms data.".format(sensor_type), "mac_id": macId}
            return res
    else:
        print("data value greater than 100")
       

def validate_sensor_data_packet_wired(data_packet):
    numeric_keys = [
        "a_rms_Axial", "a_rms_Vertical", "a_rms_Horizontal",
        # "a_p2p_Axial", "a_p2p_Vertical", "a_p2p_Horizontal",
        "v_rms_Axial", "v_rms_Vertical", "v_rms_Horizontal",
        "temperature", "acoustic_db", "acoustic_rms"
    ]
    for key in numeric_keys:
        value = data_packet.get(key)
        if value is None or not isinstance(value, (int, float)):
            print(f"Validation failed: Key '{key}' is missing or not a number.")
            return False
    return True


def validate_sensor_data_packet_ble(data_packet):
    numeric_keys = [
        "a_rms_Axial", "a_rms_Vertical", "a_rms_Horizontal",
        "a_p2p_Axial", "a_p2p_Vertical", "a_p2p_Horizontal",
        "v_rms_Axial", "v_rms_Vertical", "v_rms_Horizontal",
        "temperature"
    ]
    for key in numeric_keys:
        value = data_packet.get(key)
        if value is None or not isinstance(value, (int, float)):
            print(f"Validation failed: Key '{key}' is missing or not a number.")
            return False
    return True
