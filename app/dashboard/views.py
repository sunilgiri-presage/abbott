from audioop import rms
from concurrent.futures import thread
from pyexpat import model
import re
from sys import flags
# from turtle import pd
from unicodedata import decimal
# from typing import final
from rest_framework.parsers import JSONParser
from app import models
from app import serializers
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from django.db.models import DateTimeField, OuterRef, Subquery
from django.utils.timezone import utc
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.forms.models import model_to_dict
from app.SPFunctions.SignalProcessing import getPeak, omegaArithmetic, omegaArithmeticNew, getRMS, peakDetect, getEnvelope, getPeak_to_peak, bandPassFilter, StatFunctionsAdjustment, highPassFilter
from app.SPFunctions.fftFunctions import getFFT, FFTAnalysisTwoSide
from app.SPFunctions.EHNR import EHNR
from app.cache import load_mount_data_mapping, get_mount_data, load_sensor_orientation_mapping, get_sensor_orientation_data, load_threshold_data_mapping, load_threshold_counter_data_mapping, update_threshold_counter_data_mapping_key, update_threshold_data_mapping_key
from app.task import saveDataAsync, saveDataAcousticAsync, saveFakeAcousticData, saveMagneticDataAsync, saveRMSData
# from app.SPFunctions.kurtosis import fast_kurtogram
from scipy.stats import kurtosis
from app.thresholdFunctions import thresholdFunctions, scoreCalculations
from app.dashboard.process_save_data import saveData, saveDataAcoustic
import json
from app.cron import my_daily_task, calculateAssetHealthHistory, CalculateAssetHealthScore, checkSensorLiveStatus
from datetime import datetime, timedelta
import pytz
import calendar
from dateutil import parser
import pdb
# import math
import numpy as np
from django.db.models import Q, Max, F, Case, When, Value, IntegerField
from django.db.models.functions import Trunc
from django.db.models import  Count, DateField
from django.utils import timezone
from itertools import product
from collections import defaultdict, Counter
import asyncio
import random
from app.cron import DumpCounterDataToDatabaseV2
from app.SPFunctions.fftFunctions import getFFT, getFFT10K, getFFT20K

# import pandas as pd

# Create your views here.
local_tz = pytz.timezone("Asia/Kolkata") 
utc_tz = pytz.timezone("UTC") 
# base_url = 'http://localhost:8000/media/'
# base_url = 'https://db.presageinsights.ai/api/media/'


#result = DumpCounterDataToDatabaseV2()

#mount_mapping = load_mount_data_mapping()
#print("mount mapping loaded", len(mount_mapping))

#orientation_mapping = load_sensor_orientation_mapping()
#print("orientation mapping loaded", len(orientation_mapping))

#thresh_data = load_threshold_data_mapping()
#print("thresh_data mapping loaded", len(thresh_data))

#thresh_counter_data = load_threshold_counter_data_mapping()
#print("thresh_counter_data mapping loaded", len(thresh_counter_data))


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


#************************************ KPI Score Calculation functions ************************************

# def calculateKPIScores():
#     t1 = datetime.now()
#     scoreCalculations.calculateIndividualScore()
#     threading.Timer(10, calculateKPIScores).start()
#     t2 = datetime.now()
#     print("all calculations for calculateKPIScores are done in ", t2-t1, " seconds")
# thread1 = threading.Timer(10, calculateKPIScores)
# thread1.daemon = True
# thread1.start()
# print("state of thread 1", thread1.is_alive())



#************************************ Aggregate Score Calculation functions ************************************

# def calculateScores():
#     t1 = datetime.now()
#     scoreCalculations.calculateCombinedScore()
#     threading.Timer(10, calculateScores).start()
#     t2 = datetime.now()
#     print("all calculations for calculateCombinedScores are done in ", t2-t1, " seconds")
# thread1 = threading.Timer(15, calculateScores)
# thread1.daemon = True
# thread1.start()
# print("state of thread 1", thread1.is_alive())


#  ************************************ Both below functions moved to crontab ************************************
#************************************ Alarms and Notifications ************************************

# def checkThreshold():

#     t1 = datetime.now()
#     #checking statistical values
#     # thresholdFunctions.checkSignalStat()

#     # #checking harmonics
#     # thresholdFunctions.checkSignalHar()

#     checkSensorLiveStatus()

#     t2 = datetime.now()
#     print("all calculations are done in ", t2-t1, " seconds")
#     threading.Timer(10, checkThreshold).start()

# thread2 = threading.Timer(10, checkThreshold)
# thread2.daemon = True
# thread2.start()
# print("state of thread 2", thread2.is_alive())



#************************************ Send notification on threshold counter ************************************

# def sendNotification():
#     thresholdFunctions.checkThresholdCounter()
#     threading.Timer(5, sendNotification).start()

# thread3 = threading.Timer(5, sendNotification)
# thread3.daemon = True
# thread3.start()
# print("state of thread 3", thread3.is_alive())



#************************************ Asset health history job (cron for ec2, threading for windows) ************************************

# def assetHealthHistory():
#     CalculateAssetHealthScore()
#     threading.Timer(10, assetHealthHistory).start()

# thread4 = threading.Timer(10, assetHealthHistory)
# thread4.daemon = True
# thread4.start()
# print("state of thread 4", thread4.is_alive())




#************************************ Function to get raw data for new apis (real time data processing) ************************************

def getRawDataFn(composite_key, dataTimestamp, local_time, dataAxis, sensor_type):

    try:
        device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
        mount_id = "_"+str(device_mount_data.id)
        mount_direction = device_mount_data.mount_direction
    except:
        # return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        return {"status": "error", "message": "Sensor Mount Configurations not correct."}
    try:
        device_orientations_data = models.SensorPositionMaster.objects.get(sensor_type=sensor_type)
        mapping_obj = device_orientations_data.orientation.get(mount_direction)
        for key, value in mapping_obj.items():
            if value == dataAxis:
                raw_axis = key
    except Exception as e:
        # return Response({'message':"Sensor Position Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        return {"status": "error", "message": "Sensor Position Configurations not correct."}
    try:
        singleDeviceData = {'_id':composite_key, 'raw_axis':raw_axis}
        # pdb.set_trace()
        if dataTimestamp:
            singleDeviceData.update({'timestamp':dataTimestamp})
            try:
                raw_data = models.RawDataMaster.objects.filter(composite__endswith=mount_id, timestamp=local_time, axis=dataAxis).order_by("id")[0]
                rData = [float(i) for i in raw_data.raw_data]
                fs = raw_data.fs
                if raw_axis in ['x','y']:
                    vibrationDataRawSignal = np.multiply(rData, 0.87)
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
                try:
                    lowPass = int(rpm_data[0].get("low_pass"))
                except:
                    lowPass = 6000
                try:
                    vibrationDataUnFiltered = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
                    vibrationData = bandPassFilter(vibrationDataUnFiltered,highPass,lowPass, fs)
                except:
                    vibrationData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
                singleDeviceData.update({dataAxis: np.round(vibrationData, 4), 'no_of_samples':raw_data.no_of_samples, 'fs':fs, 'rpm':RPM, 'high_pass':highPass, 'low_pass':lowPass})
            except Exception as e:
                # return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)
                return {"status": "error", "message": "Something went wrong..."}
    except:
        # return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return {"status": "error", "message": "Something went wrong..."}

    # return singleDeviceData
    return {"status": "success", "data": singleDeviceData}



#************************************ Area Fucntions ***********************************

def CountFrequency(my_list):
      
    # Creating an empty dictionary 
    freq_list = []
    iso_flag = ['good','satisfactory','unsatisfactory','unacceptable']
    for items in iso_flag:
        if items not in my_list:
            freq_list.append({"key":items,"value":0})
        else:
            freq_list.append({"key": items,"value": my_list.count(items)})
    return freq_list

def CountFrequencyPercent(my_list):
      
    # Creating an empty dictionary 
    freq = {}
    iso_flag = ['good','satisfactory','unsatisfactory','unacceptable']
    for items in iso_flag:
        if items not in my_list:
            freq.update({items:0})
        else:
            freq[items] = int((my_list.count(items)/len(my_list))*100)
    return freq

#************************************Raw Data Fucntions***********************************

@api_view(['GET','POST'])
def raw_data_list(request):
    if request.method == 'POST':
            
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            macID = data.get("mac_id")
            sensorType = macID.split("_")[0]
            axis = data.get('axis')
            rData = data.get('raw_data')
            samplingFrequency = int(data.get('fs'))
            no_of_samples = int(data.get("no_of_samples"))
            temp = data.get("temp")

            try:
                utc_dt = datetime.utcfromtimestamp(round(datetime.now().timestamp())).replace(tzinfo=pytz.utc)  # using local timestamp from server instead of timestamp from sensors
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
            data.update({'timestamp':local_dt})

            try:
                device_data = get_mount_data(macID)
                # device_data = json.loads(device_raw_data)
                # print("---------------get_mount_data----------------", device_data)
                # device_data = models.DeviceMountMaster.objects.get(mac_id=macID, is_linked=True)
                # print("-----------------------device_data--------------------------", device_data)
                asset_id = device_data.get('asset_id')
                composite_key = device_data.get('composite_id')
                mount_id = device_data.get('id')
                sensorOrientation = device_data.get('mount_direction')
            except models.DeviceMountMaster.DoesNotExist:
                print("unmapped sensor ", macID)
                return Response({'message':'Unable to fetech device. Contact admin...'},status=status.HTTP_404_NOT_FOUND)
            
            
            if axis in ['x', 'y', 'z']:
                try:
                    if macID in ['wl_FC:B4:67:D2:8C:A4', 'wl_FC:B4:67:D2:8C:E0', 'wl_FV:B4:67:DC:22:AC', 'wl_FD:B4:67:DC:22:C0', 'wl_E8:31:CD:38:66:9C'] and axis == 'x':
                        saveFakeAcousticData(asset_id, composite_key)
                except Exception as e_a:
                    print("exception in faek acoustic", e_a)
                try:
                    axisOrientation = get_sensor_orientation_data(sensorType, sensorOrientation, axis)
                    # sesnorOrientData_raw = json.loads(sesnorOrientData_raw)
                    # sesnorOrientData = json.loads(sesnorOrientData_raw['orientation'])
                    # print("---------------------------------", sesnorOrientData.get(sensorOrientation))
                    # sesnorOrientData = models.SensorPositionMaster.objects.get(sensor_type=sensorType)
                    # axisOrientation = sesnorOrientData.get(sensorOrientation).get(axis)
                except Exception as e:
                    return Response({'message':'Something went wrong with sensor orientation data {0}'.format(e)},status=status.HTTP_404_NOT_FOUND)
                data.update({'asset_id':asset_id, "composite": composite_key, "axis": axisOrientation})
                # api_message, api_status = saveData(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp)
                # return Response({'message':api_message}, status=api_status)
                saveDataAsync.delay(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp)
                return Response({'message': 'Saving vibration data for axis {0}'.format(axis)}, status=status.HTTP_200_OK)
            
            elif axis in ['a']:
                data.update({'asset_id':asset_id, "composite": composite_key, "axis": "a"})
                # api_message, api_status = saveDataAcoustic(data, rData, samplingFrequency)
                # return Response({'message':api_message}, status=api_status)
                saveDataAcousticAsync.delay(data, rData, samplingFrequency)
                return Response({'message': 'Saving acoustic data'}, status=status.HTTP_200_OK)
            
            elif axis in ['m', 'n', 'o']:
                axisDict = {'m': 'x', 'n':'y', 'o':'z'}
                updatedAxis = axisDict[axis]
                try:
                    sesnorOrientData = models.SensorPositionMaster.objects.get(sensor_type=sensorType)
                    axisOrientation = sesnorOrientData.orientation.get(sensorOrientation).get(updatedAxis)
                except Exception as e:
                    return Response({'message':'Something went wrong with sensor orientation data {0}'.format(e)},status=status.HTTP_404_NOT_FOUND)
                data.update({'asset_id':asset_id, "composite": composite_key, "axis": axisOrientation})
                saveMagneticDataAsync.delay(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp)
                return Response({'message': 'Saving vibration data for axis {0}'.format(axis)}, status=status.HTTP_200_OK)
        
            else:
                return Response({'message':'Unidentified axis received in payload, received axis is {0}'.format(axis)},status=status.HTTP_404_NOT_FOUND)
            
            # data.update({'asset_id':asset_id, "composite": composite_key, "axis": axisOrientation})
            # saveDataAsync.delay(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp)
            # # return Response({'message':api_message}, status=api_status)
            # return Response({'message': 'Saving data'}, status=status.HTTP_200_OK)

        except Exception as e:
            print("Some exception while saving data with axis ", axis, e)
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)
        
    elif request.method == 'GET':
        rawData = models.RawDataMaster.objects.filter(mac_id='1234567')
        serializer = serializers.RawDataMasterSerializer(rawData, many=True)
        return Response(serializer.data)


#************************************Raw Data Against Device Id***********************************


@api_view(['POST'])
def device_raw_data(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            axis = data.get("axis")
            composite = data.get("composite")
            mount_id = composite.split('_')[0]
            dataType = data.get("data_type")
            timestamp = data.get("timestamp")
            singleDeviceData = {}
    
            try:
                utc_dt = datetime.fromtimestamp(timestamp).replace(tzinfo=pytz.utc)
                local_dt = utc_tz.normalize(utc_dt.astimezone(utc_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
        
            if dataType == 'raw':
                rawData = models.RawDataMaster.objects.filter(timestamp=local_dt, axis=axis, composite=composite)
                rawDataserializer = serializers.RawDataMasterSerializer(rawData[0])
                rawDataObject = json.loads(json.dumps(rawDataserializer.data))
                singleDeviceData.update({"timestamp": timestamp, \
                                         "raw_data": [float(i) for i in rawDataObject.get("raw_data")], \
                                         "sampling_rate": rawDataObject.get("fs"), \
                                         "block_size": rawDataObject.get("no_of_samples"), \
                                          "axis": rawDataObject.get("axis")  })
                try:
                    tempData = models.TemperatureMaster.objects.filter(timestamp=local_dt, composite=composite)
                    tempDataserializer = serializers.TemperatureMasterSerializer(tempData[0])
                    tempDataObject = json.loads(json.dumps(tempDataserializer.data))
                    singleDeviceData.update({"temp": float(tempDataObject.get("temp"))})
                except:
                    singleDeviceData.update({"temp": random.randint(40, 50)})
                    
                return Response({'data': singleDeviceData}, status=status.HTTP_200_OK)
            if dataType == "acceleration":
                try:
                    acc_data = models.AccelerationSpectrumMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=axis)
                    acc_data_serializer = serializers.AccelerationSpectrumMasterSerializer(acc_data[0])
                    jsondata = json.loads(json.dumps(acc_data_serializer.data))
                    singleDeviceData.update({axis:jsondata['data'], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                except:
                    return Response({'message':"Something went wrong acc spectrum"},status=status.HTTP_404_NOT_FOUND)
                try:
                    x_axis_data = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    x_axis_data_serializer = serializers.SpectrumChartDataMasterSerializer(x_axis_data[0])
                    x_axis_jsondata = json.loads(json.dumps(x_axis_data_serializer.data))
                    singleDeviceData.update({"x_axis_spectrum_data":[float(i) for i in x_axis_jsondata['acceleration']]})
                except:
                    return Response({'message':"Something went wrong x acc axis"},status=status.HTTP_404_NOT_FOUND)
                
            elif dataType == "velocity":
                try:
                    acc_data = models.VelocitySpectrumMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=axis)
                    acc_data_serializer = serializers.VelocitySpectrumMasterSerializer(acc_data[0])
                    jsondata = json.loads(json.dumps(acc_data_serializer.data))
                    singleDeviceData.update({axis:jsondata['data'], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                except:
                    return Response({'message':"Something went wrong vel spectrum"},status=status.HTTP_404_NOT_FOUND)
                try:
                    x_axis_data = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    x_axis_data_serializer = serializers.SpectrumChartDataMasterSerializer(x_axis_data[0])
                    x_axis_jsondata = json.loads(json.dumps(x_axis_data_serializer.data))
                    singleDeviceData.update({"x_axis_spectrum_data":[float(i) for i in x_axis_jsondata['acceleration']]})
                except:
                    return Response({'message':"Something went wrong x vel axis"},status=status.HTTP_404_NOT_FOUND)
                
            return Response({'data': singleDeviceData}, status=status.HTTP_200_OK)
        except:
            return Response({'message':"Something went wrong"},status=status.HTTP_404_NOT_FOUND)

        # try:
        #     rawData = models.RawDataMaster.objects.get(axis=axis, composite=composite, timestamp=local_dt)
        #     serializer = serializers.RawDataMasterSerializer(rawData)
        #     return Response({'data': serializer.data}, status=status.HTTP_200_OK)
        # except:
        #     return Response({'message':"Something went wrong"},status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({'message':"Something went wrong"},status=status.HTTP_404_NOT_FOUND)
    
class get_raw_data(APIView):

    def get(self, request, *args, **kwargs):
        try:
            composite_id = kwargs.get("param1")
            axis = kwargs.get("param2")
            idList = models.RawDataMaster.objects.filter(composite = composite_id, axis=axis).values("id", "timestamp").order_by("timestamp")
            serialData = serializers.PartialRawDataMasterSerializer(idList, many=True)
            return Response({"data": serialData.data}, status=status.HTTP_200_OK)
        except:
            return Response({"message": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)       

    def post(self, request, *args, **kwargs):
        df = JSONParser().parse(request)
        if not df:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        row_id = df.get("id")
        try:
            rawData = models.RawDataMaster.objects.get(id=row_id)
            serializer = serializers.RawDataMasterSerializer(rawData)
            return Response({'data': serializer.data}, status=status.HTTP_200_OK)
        except:
            return Response({"message": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)

#************************************Acceleration Data Fucntions***********************************

@api_view(['GET','POST'])
def acceleration_amplitude_list(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
            data.update({'timestamp':local_dt})
            serializer = serializers.AccelerationTWFMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({'message':"Data Saved"}, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':
        roles = models.AccelerationTWFMaster.objects.all()
        serializer = serializers.AccelerationTWFMasterSerializer(roles, many=True)
        return Response(serializer.data)


@api_view(['GET','POST'])
def acceleration_frequency_list(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
            data.update({'timestamp':local_dt})
            serializer = serializers.AccelerationSpectrumMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({'message':"Data Saved"}, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':
        roles = models.AccelerationSpectrumMaster.objects.all()
        serializer = serializers.AccelerationSpectrumMasterSerializer(roles, many=True)
        return Response(serializer.data)

@api_view(['POST'])
def get_acceleration_twf(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin.'},\
                status=status.HTTP_404_NOT_FOUND)

        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        
        try:
            singleDeviceData = {'_id':composite_key}
            # pdb.set_trace()
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.AccelerationTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:                         
                        acc_data = models.AccelerationTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    if not acc_data:
                        return Response({'message':'Acceleration data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.AccelerationTWFMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        singleDeviceData.update({dataAxis:[float(i) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})

                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

@api_view(['POST'])
def get_acceleration_spectrum(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            trendFunc = data.get("trendFunc")
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

        try:
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.AccelerationSpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:
                        acc_data = models.AccelerationSpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    if not acc_data:
                        return Response({'message':'Acceleration Data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.AccelerationSpectrumMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        if trendFunc == 'rms':
                            singleDeviceData.update({dataAxis: [round(float(i)*0.707,5) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                        else:
                            singleDeviceData.update({dataAxis:[round(float(i),5) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})

                        singleDeviceData.update({"max": max(singleDeviceData[dataAxis])})

                        # //////////////////////////// signal processing details ////////////////////////////
                        singleDeviceData.update({
                            "signal_processing_details":{
                                            "sampling_frequency": jsondata['fs'], "no_of_samples": jsondata['no_of_samples'], "high_pass": jsondata['high_pass'],
                                            "low_pass": jsondata['low_pass'], "rpm": jsondata['rpm']
                                                }
                                            })

                    ## need to filter data only for single axis
                    # pdb.set_trace()
                    x_axis_data = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    x_axis_data_serializer = serializers.SpectrumChartDataMasterSerializer(x_axis_data[0])
                    x_axis_jsondata = json.loads(json.dumps(x_axis_data_serializer.data))
                    singleDeviceData.update({"x_axis_spectrum_data":[float(i) for i in x_axis_jsondata['acceleration']]})

                    try:
                        accStatData = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis).order_by('-timestamp')[0]
                        singleDeviceData.update({
                            "stat_values": {
                                "rms": accStatData.rms, "axis": accStatData.axis, "peak": accStatData.peak, "peak_to_peak": accStatData.peak_to_peak
                            }
                        })
                    except:
                        singleDeviceData.update({
                            "stat_values": {
                                "rms": "Na", "axis": "Na", "peak": "Na", "peak_to_peak": "Na"
                            }
                        })


                    if not dataAxis:
                        try:
                            timestamp_list_data = models.AccelerationSpectrumMaster.objects.\
                                filter(composite__endswith=mount_id,creation_date=acc_data[0].creation_date)

                            if not timestamp_list_data:
                                return Response({'message':'Timestamp data found'},status=status.HTTP_404_NOT_FOUND)

                            timestamp_list = []
                            for singleTimestamp in timestamp_list_data:
                                acc_data_serializer = serializers.AccelerationSpectrumMasterSerializer(singleTimestamp)
                                jsondata = json.loads(json.dumps(acc_data_serializer.data))
                                local_timestamp = int(parser.isoparse(jsondata['timestamp']).timestamp())

                                if local_timestamp not in timestamp_list:
                                    timestamp_list.append(local_timestamp)
                            singleDeviceData.update({'timestamp_list':timestamp_list})

                        except:
                            return Response({'message':'Something went wrong getting timestamp list'},\
                                status=status.HTTP_404_NOT_FOUND)

                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)


        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

#************************************Velocity Fucntions***********************************

@api_view(['POST'])
def get_velocity_twf(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            # composite_key = mac_id + '_' + asset_id
            dataAxis = data.get("axis")
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)

        try:
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.VelocityTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:
                        acc_data = models.VelocityTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))  
                    if not acc_data:
                        return Response({'message':'Velocity Data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.VelocityTWFMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        singleDeviceData.update({dataAxis:jsondata['data'], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})

                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

@api_view(['POST'])
def get_velocity_spectrum(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')   

            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            trendFunc = data.get("trendFunc")
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

        try:
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.VelocitySpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:
                        acc_data = models.VelocitySpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    if not acc_data:
                        return Response({'message':'Velocity data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.VelocitySpectrumMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        if trendFunc == 'rms':
                            singleDeviceData.update({dataAxis: [round(float(i)*0.707,5) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                        else:
                            singleDeviceData.update({dataAxis:[round(float(i), 5) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                        singleDeviceData.update({"max": max(singleDeviceData[dataAxis])})
                        # //////////////////////////// signal processing details ////////////////////////////
                        singleDeviceData.update({
                            "signal_processing_details":{
                                            "sampling_frequency": jsondata['fs'], "no_of_samples": jsondata['no_of_samples'], "high_pass": jsondata['high_pass'],
                                            "low_pass": jsondata['low_pass'], "rpm": jsondata['rpm']
                                                }
                                            })

                    ## need to filter data only for single axis
                    # pdb.set_trace()
                    x_axis_data = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    x_axis_data_serializer = serializers.SpectrumChartDataMasterSerializer(x_axis_data[0])
                    x_axis_jsondata = json.loads(json.dumps(x_axis_data_serializer.data))
                    singleDeviceData.update({"x_axis_spectrum_data":[ float(i) for i in x_axis_jsondata['velocity']]})

                    try:
                        velStatData = models.VelocityStatTimeMaster.objects.get(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                        singleDeviceData.update({
                            "stat_values": {
                                "rms": velStatData.rms, "axis": velStatData.axis, "peak": velStatData.peak, "peak_to_peak": velStatData.peak_to_peak
                            }
                        })
                    except:
                        singleDeviceData.update({
                            "stat_values": {
                                "rms": "Na", "axis": "Na", "peak": "Na", "peak_to_peak": "Na"
                            }
                        })


                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

#************************************Displacement Fucntions***********************************

@api_view(['GET','POST'])
def displacement_amplitude_list(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
            data.update({'timestamp':local_dt})
            serializer = serializers.DisplacementTWFMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({'message':"Data Saved"}, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':
        roles = models.DisplacementTWFMaster.objects.all()
        serializer = serializers.DisplacementTWFMasterSerializer(roles, many=True)
        return Response(serializer.data)


@api_view(['GET','POST'])
def displacement_frequency_list(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
            data.update({'timestamp':local_dt})
            serializer = serializers.DisplacementSpectrumMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({'message':"Data Saved"}, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':
        roles = models.DisplacementSpectrumMaster.objects.all()
        serializer = serializers.DisplacementSpectrumMasterSerializer(roles, many=True)
        return Response(serializer.data)

@api_view(['POST'])
def get_displacement_twf(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

        try:
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.DisplacementTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:
                        acc_data = models.DisplacementTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    if not acc_data:
                        return Response({'message':'Displacement Data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.DisplacementTWFMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        singleDeviceData.update({dataAxis:jsondata['data'], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})

                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

@api_view(['POST'])
def get_displacement_spectrum(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            trendFunc = data.get("trendFunc")
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

        try:
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.DisplacementSpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:
                        acc_data = models.DisplacementSpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    if not acc_data:
                        return Response({'message':'Displacement Data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.DisplacementSpectrumMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        if trendFunc == 'rms':
                            singleDeviceData.update({dataAxis: [round(float(i)*0.707,5) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                        else:
                            singleDeviceData.update({dataAxis:[round(float(i), 5) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})

                        singleDeviceData.update({
                            "signal_processing_details":{
                                            "sampling_frequency": jsondata['fs'], "no_of_samples": jsondata['no_of_samples'], "high_pass": jsondata['high_pass'],
                                            "low_pass": jsondata['low_pass'], "rpm": jsondata['rpm']
                                                }
                                            })

                    ## need to filter data only for single axis
                    # pdb.set_trace()
                    x_axis_data = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    x_axis_data_serializer = serializers.SpectrumChartDataMasterSerializer(x_axis_data[0])
                    x_axis_jsondata = json.loads(json.dumps(x_axis_data_serializer.data))
                    singleDeviceData.update({"x_axis_spectrum_data":[ float(i) for i in x_axis_jsondata['displacement']]})

                    try:
                        disStatData = models.DisplacementStatTimeMaster.objects.get(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                        singleDeviceData.update({
                            "stat_values": {
                                "rms": disStatData.rms, "axis": disStatData.axis, "peak": disStatData.peak, "peak_to_peak": disStatData.peak_to_peak
                            }
                        })
                    except:
                        singleDeviceData.update({
                            "stat_values": {
                                "rms": "Na", "axis": "Na", "peak": "Na", "peak_to_peak": "Na"
                            }
                        })

                    if not dataAxis:
                        try:
                            timestamp_list_data = models.DisplacementSpectrumMaster.objects.\
                                filter(composite__endswith=mount_id,creation_date=acc_data[0].creation_date)

                            if not timestamp_list_data:
                                return Response({'message':'Timestamp data found'},status=status.HTTP_404_NOT_FOUND)

                            timestamp_list = []
                            for singleTimestamp in timestamp_list_data:
                                acc_data_serializer = serializers.DisplacementSpectrumMasterSerializer(singleTimestamp)
                                jsondata = json.loads(json.dumps(acc_data_serializer.data))
                                local_timestamp = int(parser.isoparse(jsondata['timestamp']).timestamp())

                                if local_timestamp not in timestamp_list:
                                    timestamp_list.append(local_timestamp)
                            singleDeviceData.update({'timestamp_list':timestamp_list})

                        except:
                            return Response({'message':'Something went wrong getting timestamp list'},\
                                status=status.HTTP_404_NOT_FOUND)

                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)



#************************************Velocity RMS Fucntions***********************************

@api_view(['GET', 'POST'])
def velocity_rms_list(request):
    if request.method == 'GET':
        velocity = models.VelocityStatTimeMaster.objects.all()
        serializer = serializers.VelocityStatTimeMasterSerializer(velocity, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        try:
            utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
        except:
            return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)

        raw_data = data.get("raw_data")
        samplingFrequency = int(data.get("fs"))
        axis = data.get("axis")
        mac = data.get("mac_id")
        asset_id = data.get("asset_id")
        velocity_rms = getRMS(raw_data)
        peak = getPeak(raw_data)
        peak_to_peak = getPeak_to_peak(raw_data)
        raw_data_kurt = np.array(data.get("raw_data"))

        try:
            # pdb.set_trace()
            max_kurtosis = kurtosis(raw_data_kurt)

            data = {'timestamp':local_dt,"kurtosis":round(max_kurtosis,2),"rms":velocity_rms,"axis":axis,"mac":mac,"asset_id":asset_id,\
            "peak":round(peak,2),"peak_to_peak":round(peak_to_peak,2)}
            serializer = serializers.VelocityStatTimeMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({"message": "data saved"}, status=status.HTTP_201_CREATED)
            else:
                return Response({'message':get_error_msg(serializer.errors)},status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong, kindly contact admin"},status=status.HTTP_404_NOT_FOUND)


        # if not data: 
        #     return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        # try:
        #     utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
        #     local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
        # except:
        #     return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
        # data.update({'timestamp':local_dt})
        # serializer = serializers.VelocityStatTimeMasterSerializer(data=data)
        # if serializer.is_valid():
        #     serializer.save()
        #     return Response(serializer.data, status=status.HTTP_201_CREATED)
        # return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

# @api_view(['POST'])
# def getFunctionTrendData(request):
#     if request.method == 'POST':
#         try:
#             data = JSONParser().parse(request)
#             if not data:
#                 return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
#             # encpt_data = data.get('encryption_key')
#             # finalData = encpt_data[3:-3]
#             # base64_bytes = finalData.encode('ascii')
#             # message_bytes = base64.b64decode(base64_bytes)
#             # message = message_bytes.decode('ascii')
#             # data = json.loads(message)
#             composite_key = data.get('mac_id')
#             fromDate = data.get('fromDate')
#             toDate = data.get('toDate')
#             signal_type = data.get('signalType')
#             asset_id = data.get("asset_id")
#             axisList = data.get("axis", None)
#             function = data.get("function", None)
#             sensorMacId = composite_key.split("_")[1]
#             if sensorMacId in ["E4:65:B8:2C:D3:8C", "E4:65:B8:2C:DD:60"]: ######## Form maruti sensors, sending rms values too high ########
#                 function_filter = Q(**{function + '__lte': 45}) & Q(**{function + '__isnull': False})
#             else:
#                 function_filter = Q(**{function + '__lte': 100}) & Q(**{function + '__isnull': False})
#             # search against rms_only == False to get all data points having FFT
#             sensor_type = composite_key.split("_")[0]
#             fft_only = data.get("fft_only")
#             if fft_only == False:
#                 rmsOnly = [True, False]
#             elif fft_only == True:
#                 rmsOnly = [False]
#             else:
#                 rmsOnly = [True, False]
#             # composite_key = mac_id + '_' + asset_id
#         except:
#             return Response({'message':'Something is wrong with the data. Please contact admin'},\
#                 status=status.HTTP_404_NOT_FOUND)
#         try:
#             singleDeviceData = {'_id':composite_key}
#             try:
#                 device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
#                 mount_id = "_"+str(device_mount_data.id)    # did for portable sensor as composite_id keeps on rotating
#                 # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
#             except:
#                 return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
            
#             ################################ Getting Acceleration function trend ################################
#             if signal_type == "acceleration":
#                 if (fromDate and toDate):
#                     newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
#                     newIncreasedDate = newToDate + timedelta(days=1)
#                     try:
#                         axis_data_ids = models.AccelerationStatTimeMaster.objects.filter(
#                             Q(composite__endswith=mount_id)&
#                             Q(axis__in=axisList)&
#                             Q(rms_only__in=rmsOnly)&
#                             Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])&
#                             function_filter
#                         ).values_list('id', flat=True)
#                         # Filter the queryset by these IDs
#                         axis_data = models.AccelerationStatTimeMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")

#                         if axis_data.exists():
#                             # Aggregate max value of 'rms'
#                             max_values = axis_data.aggregate(max=Max(function   ))
                            
#                             # Fetch required fields in a single query
#                             data = axis_data.values('timestamp', function, 'rms_only', 'axis')
                            
#                             function_values = [{entry['axis']: {function: entry[function]}, "flag": entry['rms_only'], "timestamp": entry['timestamp'].timestamp()} for entry in data]
                            
#                             # # Use a dictionary to ensure unique timestamps
#                             # unique_function_values = {}
#                             # for entry in data:
#                             #     timestamp = entry['timestamp'].timestamp()
#                             #     unique_function_values[timestamp] = {
#                             #         entry['axis']: {function: entry[function]},
#                             #         "flag": entry['rms_only'],
#                             #         "timestamp": timestamp
#                             #     }

#                             # # Convert the dictionary back to a list
#                             # function_values = list(unique_function_values.values())

#                         else:
#                             return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                     except models.AccelerationStatTimeMaster.DoesNotExist:
#                         return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                 else:
#                     try:
#                         axis_data_ids = models.AccelerationStatTimeMaster.objects.filter(
#                             Q(composite__endswith=mount_id) & 
#                             Q(axis__in=axisList) &
#                             Q(rms_only__in=rmsOnly) &
#                             function_filter
#                         ).order_by('-timestamp').values_list('id', flat=True)[:150]
#                         # Filter the queryset by these IDs
#                         axis_data = models.AccelerationStatTimeMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")

#                         if axis_data.exists():
#                             # Aggregate max value of 'rms'
#                             max_values = axis_data.aggregate(max=Max(function   ))
#                             # Fetch required fields in a single query
#                             data = axis_data.values('timestamp', function, 'rms_only', 'axis')
                            
#                             function_values = [{entry['axis']: {function: entry[function]}, "flag": entry['rms_only'], "timestamp": entry['timestamp'].timestamp()} for entry in data]
                            
#                             # # Use a dictionary to ensure unique timestamps
#                             # unique_function_values = {}
#                             # for entry in data:
#                             #     timestamp = entry['timestamp'].timestamp()
#                             #     unique_function_values[timestamp] = {
#                             #         entry['axis']: {function: entry[function]},
#                             #         "flag": entry['rms_only'],
#                             #         "timestamp": timestamp
#                             #     }

#                             # # Convert the dictionary back to a list
#                             # function_values = list(unique_function_values.values())

#                         else:
#                             return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                     except models.AccelerationStatTimeMaster.DoesNotExist:
#                         return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
            
#             ################################ Getting Velocity function trend ################################
#             if signal_type == "velocity":
#                 if (fromDate and toDate):
#                     newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
#                     newIncreasedDate = newToDate + timedelta(days=1)
#                     try:
#                         axis_data_ids = models.VelocityStatTimeMaster.objects.filter(
#                             Q(composite__endswith=mount_id)&
#                             Q(axis__in=axisList)&
#                             Q(rms_only__in=rmsOnly)&
#                             Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])&
#                             function_filter
#                         ).values_list('id', flat=True)
                    
#                         # Filter the queryset by these IDs
#                         axis_data = models.VelocityStatTimeMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")

#                         if axis_data.exists():
#                             # Aggregate max value of 'rms'
#                             max_values = axis_data.aggregate(max=Max(function   ))
#                             # Fetch required fields in a single query
#                             data = axis_data.values('timestamp', function, 'rms_only', 'axis')
                            
#                             function_values = [{entry['axis']: {function: entry[function]}, "flag": entry['rms_only'], "timestamp": entry['timestamp'].timestamp()} for entry in data]

#                             # # Use a dictionary to ensure unique timestamps
#                             # unique_function_values = {}
#                             # for entry in data:
#                             #     timestamp = entry['timestamp'].timestamp()
#                             #     unique_function_values[timestamp] = {
#                             #         entry['axis']: {function: entry[function]},
#                             #         "flag": entry['rms_only'],
#                             #         "timestamp": timestamp
#                             #     }

#                             # # Convert the dictionary back to a list
#                             # function_values = list(unique_function_values.values())

#                         else:
#                             return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                     except models.VelocityStatTimeMaster.DoesNotExist:
#                         return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                 else:
#                     try:
#                         t1 = datetime.now()
#                         axis_data_ids = models.VelocityStatTimeMaster.objects.filter(
#                             Q(composite__endswith=mount_id) & 
#                             Q(axis__in=axisList) &
#                             Q(rms_only__in=rmsOnly) &
#                             function_filter
#                         ).order_by('-timestamp').values_list('id', flat=True)[:150]
#                         t2 = datetime.now()
#                         axis_data = models.VelocityStatTimeMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")
#                         if axis_data.exists():
#                             # Aggregate max value of 'rms'
#                             max_values = axis_data.aggregate(max=Max(function   ))
                            
#                             # Fetch required fields in a single query
#                             data = axis_data.values('timestamp', function, 'rms_only', 'axis')
                            
#                             function_values = [{entry['axis']: {function: entry[function]}, "flag": entry['rms_only'], "timestamp": entry['timestamp'].timestamp()} for entry in data]
                            
#                             # # Use a dictionary to ensure unique timestamps
#                             # unique_function_values = {}
#                             # for entry in data:
#                             #     timestamp = entry['timestamp'].timestamp()
#                             #     unique_function_values[timestamp] = {
#                             #         entry['axis']: {function: entry[function]},
#                             #         "flag": entry['rms_only'],
#                             #         "timestamp": timestamp
#                             #     }

#                             # # Convert the dictionary back to a list
#                             # function_values = list(unique_function_values.values())

#                         else:
#                             return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                     except models.VelocityStatTimeMaster.DoesNotExist:
#                         return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
            
#             ################################ Getting Displacement function trend ################################
#             if signal_type == "displacement":
#                 if (fromDate and toDate):
#                     newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
#                     newIncreasedDate = newToDate + timedelta(days=1)
#                     try:
#                         axis_data_ids = models.DisplacementStatTimeMaster.objects.filter(
#                             Q(composite__endswith=mount_id)&
#                             Q(axis__in=axisList)&
#                             Q(rms_only__in=rmsOnly)&
#                             Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])&
#                             function_filter
#                         ).values_list('id', flat=True)
                    
#                         # Filter the queryset by these IDs
#                         axis_data = models.DisplacementStatTimeMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")

#                         if axis_data.exists():
#                             # Aggregate max value of 'rms'
#                             max_values = axis_data.aggregate(max=Max(function   ))
                            
#                             # Fetch required fields in a single query
#                             data = axis_data.values('timestamp', function, 'rms_only', 'axis')
                            
#                             function_values = [{entry['axis']: {function: entry[function]}, "flag": entry['rms_only'], "timestamp": entry['timestamp'].timestamp()} for entry in data]

#                             # # Use a dictionary to ensure unique timestamps
#                             # unique_function_values = {}
#                             # for entry in data:
#                             #     timestamp = entry['timestamp'].timestamp()
#                             #     unique_function_values[timestamp] = {
#                             #         entry['axis']: {function: entry[function]},
#                             #         "flag": entry['rms_only'],
#                             #         "timestamp": timestamp
#                             #     }

#                             # # Convert the dictionary back to a list
#                             # function_values = list(unique_function_values.values())

#                         else:
#                             return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                     except models.DisplacementStatTimeMaster.DoesNotExist:
#                         return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                 else:
#                     try:
#                         axis_data_ids = models.DisplacementStatTimeMaster.objects.filter(
#                             Q(composite__endswith=mount_id) & 
#                             Q(axis__in=axisList) &
#                             Q(rms_only__in=rmsOnly) &
#                             function_filter
#                         ).order_by('-timestamp').values_list('id', flat=True)[:150]
                    
#                         # Filter the queryset by these IDs
#                         axis_data = models.DisplacementStatTimeMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")

#                         if axis_data.exists():
#                             # Aggregate max value of 'rms'
#                             max_values = axis_data.aggregate(max=Max(function   ))
                            
#                             # Fetch required fields in a single query
#                             data = axis_data.values('timestamp', function, 'rms_only', 'axis')
                            
#                             function_values = [{entry['axis']: {function: entry[function]}, "flag": entry['rms_only'], "timestamp": entry['timestamp'].timestamp()} for entry in data]

#                             # # Use a dictionary to ensure unique timestamps
#                             # unique_function_values = {}
#                             # for entry in data:
#                             #     timestamp = entry['timestamp'].timestamp()
#                             #     unique_function_values[timestamp] = {
#                             #         entry['axis']: {function: entry[function]},
#                             #         "flag": entry['rms_only'],
#                             #         "timestamp": timestamp
#                             #     }

#                             # # Convert the dictionary back to a list
#                             # function_values = list(unique_function_values.values())

#                         else:
#                             return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
#                     except models.DisplacementStatTimeMaster.DoesNotExist:
#                         return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    
#             if len(axisList) > 1:
#                 # Create a dictionary to store merged data
#                 merged_data = defaultdict(dict)

#                 # Merge elements based on timestamp
#                 for item in function_values:
#                     timestamp = item["timestamp"]
#                     for key, value in item.items():
#                         if key != "timestamp":
#                             merged_data[timestamp][key] = value

#                 if sensor_type in ['w', 'ble']:
#                     # Filter out timestamps where any of the keys are missing
#                     filtered_data = {ts: data for ts, data in merged_data.items() if all(key in data for key in ["Axial", "Vertical", "Horizontal"])}
#                 elif sensor_type in ['wl', 'p']:
#                     # Insert 'NA' for missing keys
#                     for ts, data in merged_data.items():
#                         for key in ["Axial", "Vertical", "Horizontal"]:
#                             if key not in data:
#                                 data[key] = {function: 'NA'}
#                     filtered_data = merged_data

#                 # Convert filtered data back to a list
#                 merged_list = [{"timestamp": ts, **data} for ts, data in filtered_data.items()]
                
#             else:
#                 merged_list = function_values

#             # print("-----------------------", merged_list)


#             if len(axisList) == 1:
#                 """Function threshold values"""
#                 try:
#                     thresholdData = models.ThresholdValues.objects.get(composite__endswith=mount_id, signal_type=signal_type, axis=axisList[0], domain='time')
#                     amp_one = getattr(thresholdData, function+"_amp_level_1")
#                     amp_two = getattr(thresholdData, function+"_amp_level_2")
#                     amp_three = getattr(thresholdData, function+"_amp_level_3")
#                     maxForGraph = max(max_values['max'], amp_one, amp_two, amp_three)
#                     singleDeviceData.update({"thres": {function+"_amp_level_1": amp_one, function+"_amp_level_2": amp_two, function+"_amp_level_3": amp_three}})
#                 except Exception as e:
#                     print("exception in get_function_trend_data", e)
#                     maxForGraph = max_values['max']
#                     singleDeviceData.update({"thres": None})

#                 """Moving average trend line"""
#                 window_size = 5
#                 start = int(window_size/2)
#                 stop = window_size-start
#                 moving_avg_rms = []
#                 for i in range(0, len(function_values)):

#                     if i < window_size - 1:
#                         moving_avg_rms.append(round(float(np.mean([ i.get(axisList[0]).get(function) for i in function_values[0:i+1]])), 3))
#                     else:
#                         moving_avg_rms.append(round(float(np.mean([ i.get(axisList[0]).get(function) for i in function_values[i-window_size+1:i+1]])), 3))

#                 singleDeviceData.update({
#                     "trendData": function_values,
#                     "max": {function: maxForGraph},
#                     'moving_average': {function: moving_avg_rms}
#                     })
#             else:
#                 singleDeviceData.update({
#                     "trendData": merged_list,
#                     "max": {function: max_values['max']},
#                     })
#             return Response(singleDeviceData, status=status.HTTP_200_OK)
#         except Exception as e:
#             print("exception", e)
#             return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)




@api_view(['POST'])
def getFunctionTrendData(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            fromDate = data.get('fromDate')
            toDate = data.get('toDate')
            signal_type = data.get('signalType')
            asset_id = data.get("asset_id")
            axisList = data.get("axis", None)
            function = data.get("function", None)
            sensorMacId = composite_key.split("_")[1]

            fields = [f"{function}_{axis}" for axis in axisList]
            function_filter = Q()
            for field in fields:
                function_filter &= Q(**{f"{field}__lte": 100}) & Q(**{f"{field}__isnull": False})
            sensor_type = composite_key.split("_")[0]
            fft_only = data.get("fft_only")
            if fft_only == False:
                rmsOnly = [True, False]
            elif fft_only == True:
                rmsOnly = [False]
            else:
                rmsOnly = [True, False]
            # composite_key = mac_id + '_' + asset_id
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        try:
            singleDeviceData = {'_id':composite_key}
            try:
                device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                mount_id = "_"+str(device_mount_data.id)    # did for portable sensor as composite_id keeps on rotating
                newMount = device_mount_data.id
            except:
                return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
            
            ################################ Getting Acceleration function trend ################################
            if signal_type == "acceleration":
                if (fromDate and toDate):
                    newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                    newIncreasedDate = newToDate + timedelta(days=1)
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.AccelerationStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount)&
                            Q(rms_only__in=rmsOnly)&
                            Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])&
                            function_filter
                        )
                        axis_data = axis_data_queryset.order_by('timestamp').values(*newFields)

                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in axis_data:
                                transformed_item = {
                                    # "timestamp": normalize_to_nearest_minute(row['timestamp'].timestamp()),
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.AccelerationStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    
                else:
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.AccelerationStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount) & 
                            Q(rms_only__in=rmsOnly) &
                            function_filter
                        ).order_by('-timestamp')[:150]
                        axis_data = axis_data_queryset.values(*newFields)
                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in reversed(axis_data):
                                transformed_item = {
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.AccelerationStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    
            
            ################################ Getting Velocity function trend ################################
            if signal_type == "velocity":
                newMount = device_mount_data.id
                if (fromDate and toDate):
                    newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                    newIncreasedDate = newToDate + timedelta(days=1)
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.VelocityStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount)&
                            Q(rms_only__in=rmsOnly)&
                            Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])&
                            function_filter
                        )
                        axis_data = axis_data_queryset.order_by('timestamp').values(*newFields)
                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in axis_data:
                                transformed_item = {
                                    # "timestamp": normalize_to_nearest_minute(row['timestamp'].timestamp()),
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.VelocityStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                else:
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.VelocityStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount) & 
                            Q(rms_only__in=rmsOnly) &
                            function_filter
                        ).order_by('-timestamp')[:150]
                        axis_data = axis_data_queryset.values(*newFields)
                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in reversed(axis_data):
                                transformed_item = {
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.VelocityStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
            
            ################################ Getting Displacement function trend ################################
            if signal_type == "displacement":
                if (fromDate and toDate):
                    newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                    newIncreasedDate = newToDate + timedelta(days=1)
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.DisplacementStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount)&
                            Q(rms_only__in=rmsOnly)&
                            Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])&
                            function_filter
                        )
                        axis_data = axis_data_queryset.order_by('timestamp').values(*newFields)
                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in axis_data:
                                transformed_item = {
                                    # "timestamp": normalize_to_nearest_minute(row['timestamp'].timestamp()),
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.DisplacementStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                else:
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.DisplacementStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount) & 
                            Q(rms_only__in=rmsOnly) &
                            function_filter
                        ).order_by('-timestamp')[:150]
                        axis_data = axis_data_queryset.values(*newFields)
                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in reversed(axis_data):
                                transformed_item = {
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.DisplacementStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)


            ################################ Getting Envvelop function trend ################################
            if signal_type == "envelope":
                if (fromDate and toDate):
                    newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                    newIncreasedDate = newToDate + timedelta(days=1)
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.AccelerationEnvelopeStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount)&
                            Q(rms_only__in=rmsOnly)&
                            Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])&
                            function_filter
                        )
                        axis_data = axis_data_queryset.order_by('timestamp').values(*newFields)
                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in axis_data:
                                transformed_item = {
                                    # "timestamp": normalize_to_nearest_minute(row['timestamp'].timestamp()),
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.AccelerationEnvelopeStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                else:
                    try:
                        newFields = ['timestamp', 'rms_only'] + fields
                        axis_data_queryset = models.AccelerationEnvelopeStatTimeOptimized.objects.filter(
                            Q(mount_id=newMount) & 
                            Q(rms_only__in=rmsOnly) &
                            function_filter
                        ).order_by('-timestamp')[:150]
                        axis_data = axis_data_queryset.values(*newFields)
                        if axis_data.exists():
                            aggregation_dict = {f"max_{field}": Max(field) for field in fields}
                            max_values_dict = axis_data_queryset.aggregate(**aggregation_dict)
                            max_value = max(filter(None, max_values_dict.values()))
                            max_values = {"max": float(max_value)}
                            function_values = []
                            for row in reversed(axis_data):
                                transformed_item = {
                                    "timestamp": row['timestamp'].timestamp(),
                                    "flag": row['rms_only']
                                }
                                for key, value in row.items():
                                    if key.startswith(function+"_") and key != "rms_only":
                                        axis_name = key.replace(function+"_", "")
                                        transformed_item[axis_name] = {function: float(value)}
                                function_values.append(transformed_item)
                        else:
                            return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    except models.AccelerationEnvelopeStatTimeOptimized.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                    
            if len(axisList) > 1:
                # Create a dictionary to store merged data
                merged_data = defaultdict(dict)

                # Merge elements based on timestamp
                for item in function_values:
                    timestamp = item["timestamp"]
                    for key, value in item.items():
                        if key != "timestamp":
                            merged_data[timestamp][key] = value

                if sensor_type in ['w']:
                    # Filter out timestamps where any of the keys are missing
                    filtered_data = {ts: data for ts, data in merged_data.items() if all(key in data for key in ["Axial", "Vertical", "Horizontal"])}
                elif sensor_type in ['wl', 'p', 'ble']:
                    # Insert 'NA' for missing keys
                    for ts, data in merged_data.items():
                        for key in ["Axial", "Vertical", "Horizontal"]:
                            if key not in data:
                                data[key] = {function: 'NA'}
                    filtered_data = merged_data

                # Convert filtered data back to a list
                merged_list = [{"timestamp": ts, **data} for ts, data in filtered_data.items()]
                
            else:
                merged_list = function_values

            # print("-----------------------", merged_list)


            if len(axisList) == 1:
                """Function threshold values"""
                try:
                    thresholdData = models.ThresholdValues.objects.get(composite__endswith=mount_id, signal_type=signal_type, axis=axisList[0], domain='time')
                    amp_one = getattr(thresholdData, function+"_amp_level_1")
                    amp_two = getattr(thresholdData, function+"_amp_level_2")
                    amp_three = getattr(thresholdData, function+"_amp_level_3")
                    maxForGraph = max(max_values['max'], amp_one, amp_two, amp_three)
                    singleDeviceData.update({"thres": {function+"_amp_level_1": amp_one, function+"_amp_level_2": amp_two, function+"_amp_level_3": amp_three}})
                except Exception as e:
                    print("exception in get_function_trend_data", e)
                    maxForGraph = max_values['max']
                    singleDeviceData.update({"thres": None})

                """Moving average trend line"""
                window_size = 5
                start = int(window_size/2)
                stop = window_size-start
                moving_avg_rms = []
                for i in range(0, len(function_values)):

                    if i < window_size - 1:
                        moving_avg_rms.append(round(float(np.mean([ i.get(axisList[0]).get(function) for i in function_values[0:i+1]])), 3))
                    else:
                        moving_avg_rms.append(round(float(np.mean([ i.get(axisList[0]).get(function) for i in function_values[i-window_size+1:i+1]])), 3))

                singleDeviceData.update({
                    "trendData": function_values,
                    "max": {function: maxForGraph},
                    'moving_average': {function: moving_avg_rms}
                    })
            else:
                singleDeviceData.update({
                    "trendData": merged_list,
                    "max": {function: max_values['max']},
                    })
            return Response(singleDeviceData, status=status.HTTP_200_OK)
        except Exception as e:
            print("exception", e)
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)





#************************************Harmonics Fucntions***********************************

@api_view(['GET', 'POST'])
def harmonics_list(request):
    if request.method == 'GET':
        harmonics = models.AccelerationHarmonicsMaster.objects.all()
        serializer = serializers.AccelerationHarmonicsMasterSerializer(harmonics, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        try:
            utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
        except:
            return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
        data.update({'timestamp':local_dt})
        serializer = serializers.AccelerationHarmonicsMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def get_harmonics_data(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            signalType = data.get('signal')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)

        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)

        try:
            # pdb.set_trace()
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if signalType == 'acceleration':
                        har_data = models.AccelerationHarmonicsMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'),axis=dataAxis)
                        if not har_data:
                            return Response({'message':'Harmonics Data not found'},status=status.HTTP_404_NOT_FOUND)
                        harmonic_data_serializer = serializers.AccelerationHarmonicsMasterSerializer(har_data[0])

                    elif signalType == 'velocity':
                        har_data = models.VelocityHarmonicsMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'),axis=dataAxis)
                        if not har_data:
                            return Response({'message':'Harmonics Data not found'},status=status.HTTP_404_NOT_FOUND)
                        harmonic_data_serializer = serializers.VelocityHarmonicsMasterSerializer(har_data[0])

                    elif signalType == 'displacement':
                        har_data = models.DisplacementHarmonicsMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'),axis=dataAxis)
                        if not har_data:
                            return Response({'message':'Harmonics Data not found'},status=status.HTTP_404_NOT_FOUND)
                        harmonic_data_serializer = serializers.DisplacementHarmonicsMasterSerializer(har_data[0])
                    finalData = {}
                    amp = []
                    freq = []
                    chartData = []

                    amp = [
                        float(harmonic_data_serializer.data['one_amp']),
                        float(harmonic_data_serializer.data['two_amp']),
                        float(harmonic_data_serializer.data['three_amp']),
                        float(harmonic_data_serializer.data['four_amp']),
                        float(harmonic_data_serializer.data['five_amp'])
                    ]

                    freq = [
                        float(harmonic_data_serializer.data['one_freq']),
                        float(harmonic_data_serializer.data['two_freq']),
                        float(harmonic_data_serializer.data['three_freq']),
                        float(harmonic_data_serializer.data['four_freq']),
                        float(harmonic_data_serializer.data['five_freq'])
                    ]
                    finalData['harmonics'] = True


                    # for key,value in harmonic_data_serializer.data.items():
                    #     if key.endswith('_amp'):
                    #         amp.append(float(value))
                    #     elif key.endswith('_freq'):
                    #         freq.append(float(value))
                    #         if float(value) > 10:
                    #             finalData['harmonics'] = True
                    #         else:
                    #             finalData['harmonics'] = False
                    #     else:
                    #         pass
                    
                    freq.append(freq[0]+freq[-1])
                    freq.append(freq[0]+freq[-1])
                    freq.append(freq[0]+freq[-1])
                    # for i,j in zip(freq,amp):
                    #     chartData.append([np.round(float(i),3),np.round(float(j),3)])
                    harmonicData = {'amp':amp,'freq':freq}
                    finalData['mac_id'] = harmonic_data_serializer.data["composite"]
                    finalData['timestamp'] = harmonic_data_serializer.data['timestamp']
                    finalData['axis'] = harmonic_data_serializer.data['axis']
                    # finalData['axis'] = getattr(harmonic_data_serializer, dataAxis)
                    finalData['phase'] = harmonic_data_serializer.data['phase']
                    finalData['asset_id'] = harmonic_data_serializer.data['asset_id']
                    finalData['data'] = harmonicData
                    # finalData['chartData'] = chartData
                    finalData['signal'] = signalType

                    # return Response(acc_data_serializer.data)
                    return Response(finalData)

                except Exception as e1:
                    finalData = {}
                    print("exceptionnnnnnnnnnnnnnnnnnn e1", e1)
                    finalData['harmonics'] = False
                    return Response(finalData)
                    # return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

            else:
                return Response({'message':'Timestamp not found...'},status=status.HTTP_404_NOT_FOUND)

        except Exception as e2:
            print("exceptionnnnnnnnnnnnnnnnnnnn e2", e2)
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def harmonics_filter_data(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            mac_id = data.get('mac_id')
            axis_ids = data.get('axis_ids')
            axis = data.get('axis')
            fromDate = data.get('fromDate')
            toDate = data.get('toDate')
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)

        try:
            singleDeviceData = {'_id':mac_id}

            if (fromDate and toDate): 
                axis_data = models.AccelerationHarmonicsMaster.objects.\
                    filter(macmac=mac_id,axis=axis,creation_date__range=[fromDate,toDate])
                
                individualData = []

                if axis_data:
                    for singleaxis in axis_data:
                        vel_data_serializer = serializers.AccelerationHarmonicsMasterSerializer(singleaxis)
                        jsondata = json.loads(json.dumps(vel_data_serializer.data))
                        localtimestamp = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        singleTimestamp = {'timestamp':localtimestamp,'axis':jsondata['axis'],\
                            'phase':jsondata['axis']}
                        for singleId in axis_ids:
                            singleTimestamp.update({singleId:jsondata[singleId]})
                        individualData.append(singleTimestamp)
                
                else:
                    return Response({'message':'Harmonics data not found'},status=status.HTTP_404_NOT_FOUND)
                singleDeviceData.update({'data':individualData})
            else:
                try:
                    timestamp_data = models.AccelerationHarmonicsMaster.objects.\
                        filter(mac=mac_id,axis=axis).latest('timestamp')
                except models.AccelerationHarmonicsMaster.DoesNotExist:
                    return Response({'message':'Harmonics data not found'},status=status.HTTP_404_NOT_FOUND)
                axis_data = models.AccelerationHarmonicsMaster.objects.\
                    filter(mac=mac_id,axis=axis,\
                        creation_date__range=[(timestamp_data.creation_date-timedelta(days=30)).isoformat(),\
                        timestamp_data.creation_date])
                
                individualData = []

                if axis_data:
                    for singleaxis in axis_data:
                        vel_data_serializer = serializers.AccelerationHarmonicsMasterSerializer(singleaxis)
                        jsondata = json.loads(json.dumps(vel_data_serializer.data))
                        localtimestamp = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        singleTimestamp = {'timestamp':localtimestamp,'axis':jsondata['axis'],\
                            'phase':jsondata['axis']}
                        for singleId in axis_ids:
                            singleTimestamp.update({singleId:jsondata[singleId]})
                        individualData.append(singleTimestamp)
                else:
                    return Response({'message':'Harmonics data not found'},status=status.HTTP_404_NOT_FOUND)
                singleDeviceData.update({'data':individualData})
            return Response(singleDeviceData,status=status.HTTP_200_OK)
        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)

#************************************Envelope Data Fucntions***********************************

@api_view(['GET','POST'])
def envelope_amplitude_list(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
            data.update({'timestamp':local_dt})
            serializer = serializers.EnvelopeTWFMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({'message':"Data Saved"}, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':
        roles = models.EnvelopeTWFMaster.objects.all()
        serializer = serializers.EnvelopeTWFMasterSerializer(roles, many=True)
        return Response(serializer.data)


@api_view(['GET','POST'])
def envelope_frequency_list(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
            data.update({'timestamp':local_dt})
            serializer = serializers.EnvelopeSpectrumMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({'message':"Data Saved"}, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':
        roles = models.EnvelopeSpectrumMaster.objects.all()
        serializer = serializers.EnvelopeSpectrumMasterSerializer(roles, many=True)
        return Response(serializer.data)

@api_view(['POST'])
def get_envelope_twf(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)

        try:
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.EnvelopeTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:
                        acc_data = models.EnvelopeTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    if not acc_data:
                        return Response({'message':'Envelope Data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.EnvelopeTWFMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        singleDeviceData.update({dataAxis:jsondata['data'], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                    if not dataAxis:
                        try:
                            timestamp_list_data = models.EnvelopeTWFMaster.objects.\
                                filter(composite__endswith=mount_id,creation_date=acc_data[0].creation_date)

                            if not timestamp_list_data:
                                return Response({'message':'Timestamp data found'},status=status.HTTP_404_NOT_FOUND)

                            timestamp_list = []
                            for singleTimestamp in timestamp_list_data:
                                acc_data_serializer = serializers.EnvelopeTWFMasterSerializer(singleTimestamp)
                                jsondata = json.loads(json.dumps(acc_data_serializer.data))
                                local_timestamp = int(parser.isoparse(jsondata['timestamp']).timestamp())

                                if local_timestamp not in timestamp_list:
                                    timestamp_list.append(local_timestamp)
                            singleDeviceData.update({'timestamp_list':timestamp_list})

                        except:
                            return Response({'message':'Something went wrong getting timestamp list'},\
                                status=status.HTTP_404_NOT_FOUND)

                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

            else:
                try:
                    acc_data = models.EnvelopeTWFMaster.objects.\
                        filter(composite__endswith=mount_id).latest('timestamp')
                    if acc_data:
                        axis_data = models.EnvelopeTWFMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=acc_data.timestamp)
                        if axis_data:
                            for singleaxis in axis_data:
                                acc_data_serializer = serializers.EnvelopeTWFMasterSerializer(singleaxis)
                                jsondata = json.loads(json.dumps(acc_data_serializer.data))
                                singleDeviceData.update({'timestamp':int(parser.isoparse(jsondata['timestamp']).timestamp()),\
                                    jsondata['axis']:jsondata['data']})
                        try:
                            timestamp_list_data = models.EnvelopeTWFMaster.objects.\
                                filter(composite__endswith=mount_id,creation_date=acc_data.creation_date)

                            if not timestamp_list_data:
                                return Response({'message':'Timestamp data found'},status=status.HTTP_404_NOT_FOUND)

                            timestamp_list = []
                            for singleTimestamp in timestamp_list_data:
                                acc_data_serializer = serializers.EnvelopeTWFMasterSerializer(singleTimestamp)
                                jsondata = json.loads(json.dumps(acc_data_serializer.data))
                                local_timestamp = int(parser.isoparse(jsondata['timestamp']).timestamp())

                                if local_timestamp not in timestamp_list:
                                    timestamp_list.append(local_timestamp)
                            singleDeviceData.update({'timestamp_list':timestamp_list})

                        except:
                            return Response({'message':'Something went wrong getting timestamp list'},\
                                status=status.HTTP_404_NOT_FOUND)

                except models.EnvelopeTWFMaster.DoesNotExist:
                    return Response({'message':'Envelope Data not found'},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

@api_view(['POST'])
def get_envelope_spectrum(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            # composite_key = mac_id + '_' + asset_id
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

        try:
            singleDeviceData = {'_id':composite_key}
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    if dataAxis:
                        acc_data = models.EnvelopeSpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    else:
                        acc_data = models.EnvelopeSpectrumMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    if not acc_data:
                        return Response({'message':'Envelope Data not found'},status=status.HTTP_404_NOT_FOUND)
                    acc_data_serializer = serializers.EnvelopeSpectrumMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        singleDeviceData.update({dataAxis:[round(float(i), 5) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                        singleDeviceData.update({"max": round(max(singleDeviceData[dataAxis]), 4)})

                    x_axis_data = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
                    x_axis_data_serializer = serializers.SpectrumChartDataMasterSerializer(x_axis_data[0])
                    x_axis_jsondata = json.loads(json.dumps(x_axis_data_serializer.data))
                    # singleDeviceData.update({"x_axis_spectrum_data":x_axis_jsondata['acceleration']})
                    singleDeviceData.update({"x_axis_spectrum_data":[float(i) for i in x_axis_jsondata['acceleration']]})


                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

#************************************Logic Fucntions***********************************

@api_view(['POST'])
def get_timestamp(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            mac_id = data.get('mac_id')
            fromDate = data.get('fromDate')
            toDate = data.get('toDate')
            data_type = data.get('data_type')
            wave_type = data.get('wave_type')
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)

        try:
            singleDeviceData = {'_id':mac_id,'data_type':data_type,'wave_type':wave_type}
            timestampList = []
            if data_type == 'acceleration':
                if wave_type == "amplitude":
                    acc_data = models.AccelerationTWFMaster.objects.\
                        filter(mac=mac_id,creation_date__gte=fromDate,creation_date__lte=toDate)
                    
                    if not acc_data:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    acc_data_serializer = serializers.AccelerationTWFMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        data_dt = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        if data_dt not in timestampList:
                            timestampList.append(data_dt)

                    singleDeviceData.update({'timestamp':timestampList})

                elif wave_type == 'frequency':
                    acc_data = models.AccelerationSpectrumMaster.objects.\
                        filter(mac=mac_id,creation_date__range=[fromDate,toDate])

                    if not acc_data:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    acc_data_serializer = serializers.AccelerationSpectrumMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        data_dt = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        if data_dt not in timestampList:
                            timestampList.append(data_dt)

                    singleDeviceData.update({'timestamp':timestampList})

                else:
                    return Response({'message':'amplitude, and frequency are the only available wavetype'},\
                        status=status.HTTP_404_NOT_FOUND)

            elif data_type == 'velocity':
                if wave_type == "amplitude":
                    acc_data = models.VelocityTWFMaster.objects.\
                        filter(mac=mac_id,creation_date__range=[fromDate,toDate])

                    if not acc_data:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    acc_data_serializer = serializers.VelocityTWFMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        data_dt = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        if data_dt not in timestampList:
                            timestampList.append(data_dt)

                    singleDeviceData.update({'timestamp':timestampList})

                elif wave_type == 'frequency':
                    acc_data = models.VelocitySpectrumMaster.objects.\
                        filter(mac=mac_id,creation_date__range=[fromDate,toDate])

                    if not acc_data:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    acc_data_serializer = serializers.VelocitySpectrumMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        data_dt = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        if data_dt not in timestampList:
                            timestampList.append(data_dt)

                    singleDeviceData.update({'timestamp':timestampList})

                else:
                    return Response({'message':'amplitude, and frequency are the only available wavetype'},\
                        status=status.HTTP_404_NOT_FOUND)

            elif data_type == 'displacement':
                if wave_type == "amplitude":
                    acc_data = models.DisplacementTWFMaster.objects.\
                        filter(mac=mac_id,creation_date__range=[fromDate,toDate])
                    timestampList = []
                    if not acc_data:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    acc_data_serializer = serializers.DisplacementTWFMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        data_dt = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        if data_dt not in timestampList:
                            timestampList.append(data_dt)

                    if not timestampList:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    singleDeviceData.update({'timestamp':timestampList})
                elif wave_type == 'frequency':
                    acc_data = models.DisplacementSpectrumMaster.objects.\
                        filter(mac=mac_id,creation_date__range=[fromDate,toDate])
                    timestampList = []
                    if not acc_data:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    acc_data_serializer = serializers.DisplacementSpectrumMasterSerializer(acc_data, many=True)
                    for singleData in acc_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        data_dt = int(parser.isoparse(jsondata['timestamp']).timestamp())
                        if data_dt not in timestampList:
                            timestampList.append(data_dt)

                    if not timestampList:
                        return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)

                    singleDeviceData.update({'timestamp':timestampList})

                else:
                    return Response({'message':'amplitude, and frequency are the only available wavetype'},\
                        status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'message':'acceleration, velocity, and displacement are the only available datatype'},\
                    status=status.HTTP_404_NOT_FOUND)
            if not timestampList:
                return Response({'message':'Timestamp not found for this date range'},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)


@api_view(['POST'])
def get_device_location(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            # encpt_data = data.get('encryption_key')
            # finalData = encpt_data[3:-3]
            # base64_bytes = finalData.encode('ascii')
            # message_bytes = base64.b64decode(base64_bytes)
            # message = message_bytes.decode('ascii')
            # data = json.loads(message)
            mac_id = data.get('mac_id')
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        finalAssetData = {'mac_id':mac_id}

        try:
            mountData = models.DeviceMountMaster.objects.get(mac=mac_id)
            finalAssetData.update({'device_location':mountData.mount_location,\
                    'device_orientation':mountData.mount_direction})
        except models.DeviceMountMaster.DoesNotExist:
            finalAssetData.update({'device_location':'No location configured',\
                'device_orientation':'No orientation configured'})

        return Response(finalAssetData,status=status.HTTP_200_OK)

#************************************Asset Health Score Fucntions***********************************


""" apis for new dashboard kamal"""


@api_view(['GET','POST'])
def testApi(request):
    if request.method == 'POST':
        # try:
            # pdb.set_trace()
            data = JSONParser().parse(request)
            return Response(data, status=status.HTTP_200_OK)
    else:
        return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)

@api_view(['GET','POST'])
def getDevice(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        org_id = data.get("org_id")
        mac_id = data.get("mac_id")
        assets = data.get("asset_list")
        if assets:
            asset_list = [i.get("asset_id") for i in assets]
        finalAssetData = {'org_id':org_id}

        # ***************************** Get mac_id specific data when only mac_id is available *****************************
        if mac_id:
            mac_id = "_" + mac_id
            try:
                macIdData = models.DeviceMountMaster.objects.filter(org_id=org_id, mac_id__icontains=mac_id)
                if not macIdData:
                    return Response({'message':'No data found.'},status=status.HTTP_404_NOT_FOUND)
                macIdData_serializer = serializers.DeviceMountMasterSerializer(macIdData, many=True)
                finalAssetData.update({'data':macIdData_serializer.data})
                return Response(finalAssetData, status=status.HTTP_200_OK)
            except:
                return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
        # ***************************** Get list of unique mac_id when only company_code is available *****************************
        else:   
            try:
                try:
                    devices = models.DeviceMountMaster.objects.filter(org_id=org_id, mac_id__isnull=False, is_linked=True, asset_id__in=asset_list)
                except:
                    return Response({'message':'No asset found.'},status=status.HTTP_404_NOT_FOUND)
                if not devices:
                    return Response({'message':'No sensors found.'},status=status.HTTP_404_NOT_FOUND)
                
                for i in devices:
                    sensorStatusObject =  i.sensorstatusnotifications_set.all()
                    if len(sensorStatusObject) > 0:
                        i.online = sensorStatusObject.order_by('-creation_date')[0].online
                    else:
                        i.online = "Status not available"

                deviceData_serializer = serializers.DeviceMountMasterSerializer(devices, many=True)
                
                asset_details_map = {asset["asset_id"]: asset for asset in assets}

                for item in list(deviceData_serializer.data):
                    asset_id = item["asset_id"]
                    if asset_id in asset_details_map:
                        asset_details = asset_details_map[asset_id]
                        item.update(asset_details)

                finalAssetData.update({'mac_id_list':deviceData_serializer.data})
                return Response(finalAssetData, status=status.HTTP_200_OK)
            except:
                return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


# # *************************************************** Get Plot Data Time Domain for Alarms and Notifications ***************************************************
# @api_view(['POST'])
# def getPlotDataTime(request):
#     if request.method == 'POST':
#         try:
#             data = JSONParser().parse(request)
#             if not data:
#                 return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
#             composite_key = data.get('composite_key')
#             signal_type = data.get('signal_type')            # acc/vel/dis
#             stat_function = data.get('stat_function')        # rms/peal/one_amp/two_amp..
#             dataAxis = data.get('axis')                          # x/y/z
#             asset_id = data.get("assetId")
#             # composite_key = mac_id + '_' + asset_id
#         except:
#             return Response({'message':'Something is wrong with the data. Please contact admin'},\
#                 status=status.HTTP_404_NOT_FOUND)
        
#         try:
#             device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
#             mount_id = "_"+str(device_mount_data.id)
#             # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
#             # if sensor_orient_data.x == data.get("axis"):
#             #     dataAxis = 'x'
#             # elif sensor_orient_data.y == data.get("axis"):
#             #     dataAxis = 'y'
#             # elif sensor_orient_data.z == data.get("axis"):
#             #     dataAxis = 'z'
#             # else:
#             #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
#         except:
#             return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

#         try:
#             singleDeviceData = {'_id':composite_key, "axis": dataAxis, "stat_function": stat_function, "signal_type": signal_type}

#             if signal_type == "acceleration":
#                 fns = stat_function.split('_amp')[0]
#                 try:
#                     time_domain_data = models.AccelerationStatTimeMaster.objects.filter(
#                         Q(composite__endswith=mount_id)& 
#                         Q(axis=dataAxis)&
#                         Q(**{fns + '__isnull': False})
#                         ).order_by('-timestamp')[:100]
#                     timestampList = []
#                     dataList = []
#                     for df in reversed(time_domain_data):
#                         tStamp = getattr(df, 'timestamp')
#                         timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
#                         dataList.append(float(getattr(df, fns)))

#                     singleDeviceData.update({"timestamp":timestampList, "data": dataList})

#                 except models.AccelerationStatTimeMaster.DoesNotExist:
#                     return Response({'message':'Acceleration time domain data not found'},status=status.HTTP_404_NOT_FOUND)

#             elif signal_type == "velocity":
#                 fns = stat_function.split('_amp')[0]
#                 try:
#                     time_domain_data = models.VelocityStatTimeMaster.objects.filter(
#                         Q(composite__endswith=mount_id)& 
#                         Q(axis=dataAxis)&
#                         Q(**{fns + '__isnull': False})
#                         ).order_by('-timestamp')[:100]
#                     timestampList = []
#                     dataList = []
#                     for df in reversed(time_domain_data):
#                         tStamp = getattr(df, 'timestamp')
#                         timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
#                         dataList.append(float(getattr(df, fns)))

#                     singleDeviceData.update({"timestamp":timestampList, "data": dataList})

#                 except models.VelocityStatTimeMaster.DoesNotExist:
#                     return Response({'message':'Velocity time domain data not found'},status=status.HTTP_404_NOT_FOUND)

#             elif signal_type == "displacement":
#                 fns = stat_function.split('_amp')[0]
#                 try:
#                     time_domain_data = models.DisplacementStatTimeMaster.objects.filter(
#                         Q(composite__endswith=mount_id)&
#                         Q(axis=dataAxis)&
#                         Q(**{fns + '__isnull': False})
#                         ).order_by('-timestamp')[:100]
#                     timestampList = []
#                     dataList = []
#                     for df in reversed(time_domain_data):
#                         tStamp = getattr(df, 'timestamp')
#                         timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
#                         dataList.append(float(getattr(df, fns)))

#                     singleDeviceData.update({"timestamp":timestampList, "data": dataList})

#                 except models.DisplacementStatTimeMaster.DoesNotExist:
#                     return Response({'message':'Displacement time domain data not found'},status=status.HTTP_404_NOT_FOUND)

#         except Exception as e1:
#             print("exceptionnnnnnnnnnnnnnnnnnnn e1", e1)
#             return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
#         return Response(singleDeviceData,status=status.HTTP_200_OK)


# *************************************************** Get Plot Data Time Domain for Alarms and Notifications ***************************************************
@api_view(['POST'])
def getPlotDataTime(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get('composite_key')
            signal_type = data.get('signal_type')            # acc/vel/dis
            stat_function = data.get('stat_function')        # rms/peal/one_amp/two_amp..
            dataAxis = data.get('axis')                          # x/y/z
            asset_id = data.get("assetId")
            # composite_key = mac_id + '_' + asset_id
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            # mount_id = "_"+str(device_mount_data.id)
            mount_id = device_mount_data.id
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

        try:
            singleDeviceData = {'_id':composite_key, "axis": dataAxis, "stat_function": stat_function, "signal_type": signal_type}

            if signal_type == "acceleration":
                fns = stat_function.split('_amp')[0]
                try:
                    # time_domain_data = models.AccelerationStatTimeMaster.objects.filter(
                    #     Q(mount_id=mount_id)& 
                    #     Q(axis=dataAxis)&
                    #     Q(**{fns + '__isnull': False})
                    #     ).order_by('-timestamp')[:100]

                    time_domain_data = models.AccelerationStatTimeOptimized.objects.filter(
                        Q(mount_id=mount_id)& 
                        Q(**{fns + '_' + dataAxis + '__isnull': False})
                        ).order_by('-timestamp')[:100]
                    timestampList = []
                    dataList = []
                    for df in reversed(time_domain_data):
                        tStamp = getattr(df, 'timestamp')
                        timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
                        dataList.append(float(getattr(df, fns + '_' + dataAxis)))

                    singleDeviceData.update({"timestamp":timestampList, "data": dataList})

                except models.AccelerationStatTimeOptimized.DoesNotExist:
                    return Response({'message':'Acceleration time domain data not found'},status=status.HTTP_404_NOT_FOUND)

            elif signal_type == "velocity":
                fns = stat_function.split('_amp')[0]
                try:
                    # time_domain_data = models.VelocityStatTimeMaster.objects.filter(
                    #     Q(mount_id=mount_id)& 
                    #     Q(axis=dataAxis)&
                    #     Q(**{fns + '__isnull': False})
                    #     ).order_by('-timestamp')[:100]
                    time_domain_data = models.VelocityStatTimeOptimized.objects.filter(
                        Q(mount_id=mount_id)& 
                        Q(**{fns + '_' + dataAxis + '__isnull': False})
                        ).order_by('-timestamp')[:100]
                    timestampList = []
                    dataList = []
                    for df in reversed(time_domain_data):
                        tStamp = getattr(df, 'timestamp')
                        timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
                        dataList.append(float(getattr(df, fns + '_' + dataAxis)))

                    singleDeviceData.update({"timestamp":timestampList, "data": dataList})

                except models.VelocityStatTimeOptimized.DoesNotExist:
                    return Response({'message':'Velocity time domain data not found'},status=status.HTTP_404_NOT_FOUND)

            elif signal_type == "displacement":
                fns = stat_function.split('_amp')[0]
                try:
                    # time_domain_data = models.DisplacementStatTimeMaster.objects.filter(
                    #     Q(mount_id=mount_id)&
                    #     Q(axis=dataAxis)&
                    #     Q(**{fns + '__isnull': False})
                    #     ).order_by('-timestamp')[:100]
                    time_domain_data = models.DisplacementStatTimeOptimized.objects.filter(
                        Q(mount_id=mount_id)& 
                        Q(**{fns + '_' + dataAxis + '__isnull': False})
                        ).order_by('-timestamp')[:100]
                    timestampList = []
                    dataList = []
                    for df in reversed(time_domain_data):
                        tStamp = getattr(df, 'timestamp')
                        timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
                        dataList.append(float(getattr(df, fns + '_' + dataAxis)))

                    singleDeviceData.update({"timestamp":timestampList, "data": dataList})

                except models.DisplacementStatTimeMaster.DoesNotExist:
                    return Response({'message':'Displacement time domain data not found'},status=status.HTTP_404_NOT_FOUND)

        except Exception as e1:
            print("exceptionnnnnnnnnnnnnnnnnnnn e1", e1)
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

# *************************************************** Get Plot Data Frequency Domain for Alarms and Notifications ***************************************************
@api_view(['POST'])
def getPlotDataFreq(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get('composite_key')
            signal_type = data.get('signal_type')            # acc/vel/dis
            stat_function = data.get('stat_function')        # rms/peal/one_amp/two_amp..
            dataAxis = data.get('axis')                          # x/y/z
            asset_id = data.get("assetId")
            # composite_key = mac_id + '_' + asset_id
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        
        try:
            singleDeviceData = {'_id':composite_key, "axis": dataAxis, "stat_function": stat_function, "signal_type": signal_type}

            if signal_type == "acceleration":
                try:
                    freq_domain_data = models.AccelerationHarmonicsMaster.objects.filter(
                        Q(composite__endswith=mount_id)&
                        Q(axis=dataAxis)&
                        Q(**{stat_function + '__isnull': False})
                        ).order_by('-timestamp')[:100]
                    timestampList = []
                    dataList = []

                    for df in reversed(freq_domain_data):
                        tStamp = getattr(df, 'timestamp')
                        timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
                        dataList.append(float(getattr(df, stat_function)))

                    singleDeviceData.update({"timestamp":timestampList, "data": dataList})

                except models.AccelerationHarmonicsMaster.DoesNotExist:
                    return Response({'message':'Acceleration frequency domain data not found'},status=status.HTTP_404_NOT_FOUND)

            elif signal_type == "velocity":
                try:
                    freq_domain_data = models.VelocityHarmonicsMaster.objects.filter(
                        Q(composite__endswith=mount_id)&
                        Q(axis=dataAxis)&
                        Q(**{stat_function + '__isnull': False})
                        ).order_by('-timestamp')[:100]
                    timestampList = []
                    dataList = []

                    for df in reversed(freq_domain_data):
                        tStamp = getattr(df, 'timestamp')
                        timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
                        dataList.append(float(getattr(df, stat_function)))

                    singleDeviceData.update({"timestamp":timestampList, "data": dataList})

                except models.VelocityHarmonicsMaster.DoesNotExist:
                    return Response({'message':'Velocity frequency domain data not found'},status=status.HTTP_404_NOT_FOUND)

            elif signal_type == "displacement":
                try:
                    freq_domain_data = models.DisplacementHarmonicsMaster.objects.filter(
                        Q(composite__endswith=mount_id)&
                        Q(axis=dataAxis)&
                        Q(**{stat_function + '__isnull': False})
                        ).order_by('-timestamp')[:100]
                    timestampList = []
                    dataList = []
                    for df in reversed(freq_domain_data):
                        tStamp = getattr(df, 'timestamp')
                        timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
                        dataList.append(float(getattr(df, stat_function)))

                    singleDeviceData.update({"timestamp":timestampList, "data": dataList})

                except models.DisplacementHarmonicsMaster.DoesNotExist:
                    return Response({'message':'Displacement frequency domain data not found'},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

# *************************************************** Get Plot Data Temperature for Alarms and Notifications ***************************************************
@api_view(['POST'])
def getPlotDataTemp(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get('composite_key')
            signal_type = data.get('signal_type')            # acc/vel/dis
            stat_function = data.get('stat_function')        # rms/peal/one_amp/two_amp..
            axis = data.get('axis')                          # x/y/z
            asset_id = data.get("assetId")
            # composite_key = mac_id + '_' + asset_id
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin'},\
                status=status.HTTP_404_NOT_FOUND)
        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            # pdb.set_trace()
            singleDeviceData = {'_id':composite_key, "axis": axis, "stat_function": stat_function, "signal_type": signal_type}
            temp_data = models.TemperatureMaster.objects.filter(
                Q(composite__endswith=mount_id)&
                Q(**{'temp__isnull': False})
                ).order_by('-timestamp')[:100]
            timestampList = []
            dataList = []
            for df in reversed(temp_data):
                tStamp = getattr(df, 'timestamp')
                timestampList.append(int(parser.isoparse(str(tStamp)).timestamp()))
                dataList.append(float(getattr(df, "temp")))
            singleDeviceData.update({"timestamp":timestampList, "data": dataList})

        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)


# *************************************************** Threshold Data Functions ***************************************************
@api_view(['POST'])
def thresholdValues(request):
    try:
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        composite_key = data.get("composite_key")
        axis = data.get("axis")
        signal_type = data.get("signal_type")
        domain = data.get("domain")
        stat_function = data.get("stat_function")
        amp_level_1 = data.get("amp_level_1")
        amp_level_2 = data.get("amp_level_2")
        amp_level_3 = data.get("amp_level_3")
        rep_level_1 = data.get("rep_level_1")
        rep_level_2 = data.get("rep_level_2")
        rep_level_3 = data.get("rep_level_3")
        # stat_function_value = data.get("stat_function_value")
        # repetition = data.get("repetition")
        asset_id = data.get("assetId")
        # composite_key = mac_id + '_' + asset_id
        if data.get("axis") == "temp":
            dataAxis = "temp"
        else:
            dataAxis = data.get("axis")

        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = str(device_mount_data.id)
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     if data.get("axis") == 'temp':
            #         dataAxis = 'temp'
            #     else:
            #         return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)


        
        threshold_value = {
            "composite": composite_key, 
            'axis': dataAxis, 
            'signal_type': signal_type, 
            'domain': domain, 
            stat_function+'_level_1': amp_level_1, 
            stat_function+'_level_2': amp_level_2, 
            stat_function+'_level_3': amp_level_3, 
            'asset_id': asset_id,
            'mount_id': mount_id
        }
        # pdb.set_trace()

        counter_values = {
            "composite": composite_key, 
            'axis': dataAxis, 
            'signal_type': signal_type, 
            'domain': domain, 
            stat_function+'_repetition_level_1': rep_level_1, 
            stat_function+'_repetition_level_2': rep_level_2, 
            stat_function+'_repetition_level_3': rep_level_3, 
            'asset_id': asset_id,
            'mount_id': mount_id
        }

        threshold_updated = False
        counter_updated = False
        threshold_obj = None

        try:
            threshold_obj, created = models.ThresholdValues.objects.update_or_create(
                mount_id=mount_id,
                axis = dataAxis, 
                signal_type = signal_type, 
                domain = domain,
                defaults = threshold_value
            )
            threshold_updated = True
            
        except Exception as ee:
            print("exception in new flow", ee)

        thre = models.ThresholdCounterMaster.objects.filter(mount_id=mount_id, axis = dataAxis, signal_type = signal_type, domain = domain).values()


        try:
            obj, created = models.ThresholdCounterMaster.objects.update_or_create(
                mount_id=mount_id,
                axis = dataAxis, 
                signal_type = signal_type, 
                domain = domain,
                defaults = counter_values
            )
            counter_updated = True
            
        except Exception as ee:
            print("exception in new flow", ee)

        redis_key = str(mount_id) + '-' + str(dataAxis) + '-' + str(signal_type) + '-' + str(domain)

        if threshold_updated:
            try:
                update_threshold_data_mapping_key(redis_key, mount_id, dataAxis, signal_type, domain)
                print("Threshold data mapping refreshed in Redis for key:", redis_key)
            except Exception as e:
                print(f"Error refreshing threshold data mapping in Redis: {e}")

        if counter_updated:
            try:
                update_threshold_counter_data_mapping_key(redis_key, mount_id, dataAxis, signal_type, domain)
                print("Threshold counter data mapping refreshed in Redis for key:", redis_key)
            except Exception as e:
                print(f"Error refreshing threshold counter data mapping in Redis: {e}")
        
        return Response({'message':"All Data Updated"}, status=status.HTTP_201_CREATED)


    except Exception as e:
        print("-----------------------e---------------------", e)
        return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetThresholdData(request):
    try:
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

        composite_key = data.get("composite_key")
        axis = data.get("axis")
        signal_type = data.get("signal_type")
        domain = data.get("domain")
        statFunc = data.get("stat_func")
        if data.get("axis") == "temp":
            dataAxis = "temp"
        else:
            dataAxis = data.get("axis")
        thresholdDict = {"mac": composite_key, "axis": dataAxis, "domain": domain, "signal_type": signal_type}
        asset_id = data.get("assetId")
        # composite_key = mac_id + '_' + asset_id

        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     if data.get("axis") == 'temp':
            #         dataAxis = 'temp'
            #     else:
            #         return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        

        try: 
            thresholdData = models.ThresholdValues.objects.get(composite__endswith=mount_id, axis = dataAxis, signal_type = signal_type, domain = domain)
        except:
            return Response({'data':[], 'message': 'No data found for {0} {1}'.format(signal_type, statFunc)},status=status.HTTP_404_NOT_FOUND)
        try:
            # thresholdDataserializer = serializers.ThresholdValuesSerializer(thresholdData)
            # jsondata = json.loads(json.dumps(thresholdDataserializer.data))

            thresholdDict.update({"amp_level_1": getattr(thresholdData, statFunc+'_level_1')})
            thresholdDict.update({"amp_level_2": getattr(thresholdData, statFunc+'_level_2')})
            thresholdDict.update({"amp_level_3": getattr(thresholdData, statFunc+'_level_3')})

            counterData = models.ThresholdCounterMaster.objects.get(composite__endswith=mount_id, axis = dataAxis, signal_type = signal_type, domain = domain)
            # counterDataSerializer = serializers.ThresholdCounterMasterSerializer(counterData)
            # countjsondata = json.loads(json.dumps(counterDataSerializer.data))

            thresholdDict.update({"repetition_level_1": getattr(counterData, statFunc+'_repetition_level_1')})
            thresholdDict.update({"repetition_level_2": getattr(counterData, statFunc+'_repetition_level_2')})
            thresholdDict.update({"repetition_level_3": getattr(counterData, statFunc+'_repetition_level_3')})

            # jsondata.update({"counter": counterDataSerializer.get()})
            return Response({'data':thresholdDict, 'status_code': 200}, status=status.HTTP_200_OK) 
        except:
            return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
    except:
        return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetTempData(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

        composite_key = data.get("mac_id")
        if composite_key == "ble_D5:73:29:01:CA:37_66f55613bcc52d144f4140d3_3658":
            composite_key = "ble_CD:B2:F8:13:19:59_66f55613bcc52d144f4140d3_3652"
        else:
            pass
        asset_id = data.get("assetId")
        fromDate = data.get("fromDate")
        toDate = data.get("toDate")
        final_data = {"mac_id": data.get("mac_id") }
        # composite_key = mac_id + '_' + asset_id
        """returning empty result for korean ble sensor with faulty temp data"""
        if composite_key == "ble_EB:9F:B9:52:0D:1D_66f3a4f79aa4ef7c18577d55_3621":
            return Response({'message':'Temperature trend data not found'},status=status.HTTP_404_NOT_FOUND)
        else:
            pass
        try:
            try:
                device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                mount_id = "_"+str(device_mount_data.id)
            except:
                return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
            if (fromDate and toDate):
                newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                newIncreasedDate = newToDate + timedelta(days=1)
                tempData = models.TemperatureMaster.objects.filter(composite__endswith=mount_id, \
                    timestamp__range=[fromDate.split("T")[0],newIncreasedDate]).order_by('-timestamp')
                    # timestamp__range=[fromDate.split("T")[0],toDate.split("T")[0]]).order_by('-timestamp')
            else:
                try:
                    timestamp_data = models.TemperatureMaster.objects.filter(composite__endswith=mount_id).latest('timestamp')
                except models.TemperatureMaster.DoesNotExist:
                    return Response({'message':'Temperature trend data not found'},status=status.HTTP_404_NOT_FOUND)
                # pdb.set_trace()
                tempData = models.TemperatureMaster.objects.filter(composite__endswith=mount_id,\
                            timestamp__lte=timestamp_data.timestamp).order_by('-timestamp')[:150]
            tempData_serializer = serializers.TemperatureMasterSerializer(tempData, many=True)
            tempList = []
            timestampList = []
            if tempData_serializer:
                for row in reversed(tempData_serializer.data):
                    jsondata = json.loads(json.dumps(row))
                    timestampList.append(int(parser.isoparse(jsondata.get("timestamp")).timestamp()))
                    # tempList.append(float(jsondata.get("temp")))
                    if data.get("mac_id") == "ble_D5:73:29:01:CA:37_66f55613bcc52d144f4140d3_3658":
                       tempList.append(float(jsondata.get("temp"))+12) 
                    else:
                        tempList.append(float(jsondata.get("temp")))
            final_data.update({"timestamp":timestampList, "temp_data": tempList})


            try:
                thresholdData = models.ThresholdValues.objects.get(composite=composite_key, signal_type='temp', axis='temp')
            except:
                thresholdData = None
            try:
                # pdb.set_trace()
                thresholdDataSerializer = serializers.ThresholdValuesSerializer(thresholdData)
                final_data.update({"thres": thresholdDataSerializer.data})
                ls = []
                for key, value in thresholdDataSerializer.data.items():
                    if key not in ["composite", "axis", "signal_type", "domain", "asset_id"]:
                        ls.append(float(value))
                maxValue = max([max(ls), max(tempList)])
            except:
                final_data.update({"thres": None})
                maxValue = max(tempList)

            """Moving average trend line"""
            window_size = 5
            start = int(window_size/2)
            stop = window_size-start
            moving_avg_temp = []
         

            for i in range(0, len(tempList)):

                if i < window_size - 1:
                    moving_avg_temp.append(round(float(np.mean([ i for i in tempList[0:i+1]])), 3))
                else:
                    moving_avg_temp.append(round(float(np.mean([ i for i in tempList[i-window_size+1:i+1]])), 3))

            final_data.update({"max": maxValue, "moving_average": moving_avg_temp})
            return Response({'data':final_data, 'status_code': 200}, status=status.HTTP_200_OK) 
        except:
            return Response({'data':[], 'status_code': 400}, status=status.HTTP_200_OK) 
    except:
        return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
    


@api_view(['POST'])
def GetAcousticData(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

        composite_key = data.get("mac_id")
        asset_id = data.get("assetId")
        fromDate = data.get("fromDate")
        toDate = data.get("toDate")
        final_data = {"mac_id": data.get("mac_id") }
        # composite_key = mac_id + '_' + asset_id
        try:
            try:
                device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                mount_id = "_"+str(device_mount_data.id)
            except:
                return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
            if (fromDate and toDate):
                newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                newIncreasedDate = newToDate + timedelta(days=1)
                acousticData = models.AcousticsMaster.objects.filter(composite__endswith=mount_id, \
                    timestamp__range=[fromDate.split("T")[0],newIncreasedDate]).order_by('-timestamp')
                    # timestamp__range=[fromDate.split("T")[0],toDate.split("T")[0]]).order_by('-timestamp')
            else:
                try:
                    timestamp_data = models.AcousticsMaster.objects.filter(composite__endswith=mount_id).latest('timestamp')
                except models.AcousticsMaster.DoesNotExist:
                    return Response({'message':'Acoustic trend data not found'},status=status.HTTP_404_NOT_FOUND)
                # pdb.set_trace()
                acousticData = models.AcousticsMaster.objects.filter(composite__endswith=mount_id,\
                            timestamp__lte=timestamp_data.timestamp).order_by('-timestamp')[:150]
            acousticData_serializer = serializers.AcousticsMasterSerializer(acousticData, many=True)
            # acousticList = []
            # acousticList_10k = []
            # acousticList_20k = []
            # timestampList = []
            # if acousticData_serializer:
            #     for row in reversed(acousticData_serializer.data):
            #         jsondata = json.loads(json.dumps(row))
            #         timestampList.append(int(parser.isoparse(jsondata.get("timestamp")).timestamp()))
            #         acousticList.append(float(jsondata.get("acoustic_rms")))
            #         acousticList_10k.append(float(jsondata.get("acoustic_rms_10k")))
            #         acousticList_20k.append(float(jsondata.get("acoustic_rms_20k")))
            if acousticData_serializer:
                data = list(reversed(acousticData_serializer.data))
                if composite_key in ['ble_FD:A4:C8:32:9C:EB_67178104a58fd75e0c74a440_3723', 'ble_FF:4B:4F:9C:E4:34_67178104a58fd75e0c74a440_3724','ble_D9:72:23:F0:78:C2_67178104a58fd75e0c74a440_3725','ble_FE:90:0C:2E:BC:C9_67178104a58fd75e0c74a440_3726']:
                    timestampList = [int(parser.isoparse(row["timestamp"]).timestamp()) for row in data]
                    acousticList = []
                    acousticList_10k = []
                    acousticList_20k = [float(row["acoustic_rms_20k"]) for row in data]
                else:
                    timestampList = [int(parser.isoparse(row["timestamp"]).timestamp()) for row in data]
                    acousticList = [float(row["acoustic_rms"]) for row in data]
                    acousticList_10k = [float(row["acoustic_rms_10k"]) for row in data]
                    acousticList_20k = [float(row["acoustic_rms_20k"]) for row in data]
            final_data.update({"timestamp":timestampList, "acoustic_data": acousticList, "acoustic_rms_10k": acousticList_10k, "acoustic_rms_20k": acousticList_20k})
            return Response({'data':final_data, 'status_code': 200}, status=status.HTTP_200_OK) 
        except Exception as e:
            print("Exception in acoustic trend data", e)
            return Response({'data':[], 'status_code': 400}, status=status.HTTP_200_OK) 
    except:
        return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)



# deprecated  save data as per mqtt_listener file against 'wired/rms' topic
@api_view(['POST'])
def SaveWiredSensorData(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        # pdb.set_trace()
        res = saveRMSData.delay(data, 'w')
        if res.get('result') == True:
            return Response({'message': res.get('message')}, status=status.HTTP_201_CREATED)
        else:
            return Response({'message': res.get('message')}, status=status.HTTP_404_NOT_FOUND)
    except:
        return Response({'message':'Something went wrong. Contact admin...'},status=status.HTTP_404_NOT_FOUND)
    
# deprecated  save data as per mqtt_listener file against 'wired/rms' topic
@api_view(['POST'])
def SaveBleRMSSensorData(request):
    try:
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        res = saveRMSData.delay(data, 'ble')
        return Response({'message': "Data sent to celery worker for mac-id {0}".format(data.get("mac"))}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'message':'Something went wrong for mac-id {0}. Contact admin...'.format(data.get("mac"))},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetWiredSensorData(request):
    try:
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        # pdb.set_trace()
        try:
            device_data = models.DeviceModelMaster.objects.get(mac_id=data.get("mac_id"), is_linked=True)
            asset_id = device_data.asset_id
            composite_key = device_data.composite_id
        except:
            return Response({'message':'Unable to fetech device. Contact admin...'},status=status.HTTP_404_NOT_FOUND)
        final_data = {"mac_id": data.get('mac_id')}
        mac_id = data.get('mac_id')
        timestamp_list = []
        x_data = []
        y_data = []
        z_data = []
        rms_data = models.WiredSensorDataMaster.objects.filter(composite=composite_key).order_by('-timestamp')[:100]
        if rms_data:
            for row in rms_data:
                rms_data_serializer = serializers.WiredSensorDataMasterSerializer(row)
                jsondata = json.loads(json.dumps(rms_data_serializer.data))
                timestamp_list.append(jsondata.get('timestamp'))
                x_data.append(jsondata.get('x_rms'))
                y_data.append(jsondata.get('y_rms'))
                z_data.append(jsondata.get('z_rms'))
        final_data.update({'timestamp': timestamp_list, 'x': x_data, 'y': y_data, 'z': z_data})
        return Response({'data':final_data}, status=status.HTTP_200_OK)

    except:
        return Response({'message':'Unable to fetech device. Contact admin...'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetKpiValueMobile(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        # pdb.set_trace()
        dataAxis = data.get("axis")
        composite_key = data.get("composite_key")
        # try:
        #     device_data = models.DeviceModelMaster.objects.get(mac_id=data.get("mac_id"), is_linked=True)
        #     asset_id = device_data.asset_id
        #     composite_key = device_data.composite_id
        # except:
        #     return Response({'message':'Unable to fetech device. Contact admin...'},status=status.HTTP_404_NOT_FOUND)
        

        try:
            # pdb.set_trace()
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            asset_id = device_mount_data.asset_id
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        


        final_data = {"composite_key": data.get('composite_key'), "asset_id": asset_id, "axis": dataAxis}
        rms_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=dataAxis).order_by('-timestamp')
        if rms_data:
            raw_data_serializer = serializers.VelocityStatTimeMasterSerializer(rms_data[0])
            jsondata = json.loads(json.dumps(raw_data_serializer.data))
            localtimestamp = int(parser.isoparse(jsondata['timestamp']).timestamp())
            final_data.update({"velocity_rms": jsondata.get("rms"), "timstamp": localtimestamp})
        else:
            final_data.update({"velocity_rms": "Na", "timstamp": "Na"})
            # return Response({'message':"No Velocity Data Available for selected data point. Kindly collect some data"}, status=status.HTTP_404_NOT_FOUND)
        # final_data.update({"rms_data": rmsData, "asset_id": asset_id})

        acc_rms_data = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=dataAxis).order_by('-timestamp')
        if acc_rms_data:
            acc_raw_data_serializer = serializers.AccelerationStatTimeMasterSerializer(acc_rms_data[0])
            acc_jsondata = json.loads(json.dumps(acc_raw_data_serializer.data))
            # localtimestamp = int(parser.isoparse(acc_jsondata['timestamp']).timestamp())
            final_data.update({"acc_rms": acc_jsondata.get("rms")})
        else:
            final_data.update({"acc_rms": "Na"})
            # return Response({'message':"No Acceleration Data Available for selected data point. Kindly collect some data"}, status=status.HTTP_404_NOT_FOUND)

        temp_data = models.TemperatureMaster.objects.filter(composite__endswith=mount_id).order_by('-timestamp')
        if temp_data:
            temp_data_serializer = serializers.TemperatureMasterSerializer(temp_data[0])
            temp_json = json.loads(json.dumps(temp_data_serializer.data))
            final_data.update({"temp": temp_json.get("temp")})
        else:
            final_data.update({"temp": "Na"})
            # return Response({'message':"No Temperature Data Available for selected data point. Kindly collect some data"}, status=status.HTTP_404_NOT_FOUND)
        
        return Response({'data':final_data}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, kindly check after sometime.'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def SaveThresholdValues(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
        composite_key = data.get("mac_id")
        asset_id = data.get("asset_id")

        vrms_level_3 = data.get("vrms_level_2")*1.5
        acc_envelope_level_3 = data.get("acc_envelope_level_2")*1.5
        temp_level_3 = data.get("temp_level_2")*1.5

        # composite_key = mac_id + '_' + asset_id
        threshold_data = {"composite": composite_key, "asset_id": asset_id, "v_rms_level_1": data.get("vrms_level_1"),\
            "v_rms_level_2": data.get("vrms_level_2"),"v_rms_level_3": round(vrms_level_3,2),"a_envelope_level_1": data.get("acc_envelope_level_1"),\
                "a_envelope_level_2": data.get("acc_envelope_level_2"),"a_envelope_level_3": round(acc_envelope_level_3,2),\
                    "temp_level_1": data.get("temp_level_1"),"temp_level_2": data.get("temp_level_2"),"temp_level_3": round(temp_level_3,2),\
                        "axis": data.get("axis")}
        threshold_data_serializer = serializers.MobileAppKpiThresholdSerializer(data = threshold_data)
        if threshold_data_serializer.is_valid():
            threshold_data_serializer.save()
            return Response({'message': 'Data saved.'}, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(threshold_data_serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
    except:
        return Response({'message':'Something went wrong. Contact admin...'},status=status.HTTP_404_NOT_FOUND)


# @api_view(['POST'])
# def GetThresholdValues(request):
#     try:
#         data = JSONParser().parse(request)
#         if not data:
#             return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
#         composite_key = data.get("composite_key")
#         axis = data.get("axis")
#         try:
#             # pdb.set_trace()
#             thres_data = models.MobileAppKpiThreshold.objects.filter(composite=composite_key, axis=axis).values()
#             return Response({"data":thres_data[0]}, status=status.HTTP_200_OK)
#         except:
#             return Response({'message':'No data found, kindly set some threshold values.'}, status=status.HTTP_404_NOT_FOUND)

#     except:
#         return Response({'message':'Something went wrong. Contact admin...'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetThresholdValuesMobile(request):
    try:
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        composite_key = data.get("composite_key")
        dataAxis = data.get("axis")
        signal_type = ['acceleration','velocity','temp']
        domain = 'time'
        thresholdDict = {"composite_key": composite_key, "axis": dataAxis, "domain": domain}

        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
            asset_id = device_mount_data.asset_id
            # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            # if sensor_orient_data.x == data.get("axis"):
            #     dataAxis = 'x'
            # elif sensor_orient_data.y == data.get("axis"):
            #     dataAxis = 'y'
            # elif sensor_orient_data.z == data.get("axis"):
            #     dataAxis = 'z'
            # else:
            #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)

        # composite_key = mac_id + '_' + asset_id
        try: 
            thresholdData = models.ThresholdValues.objects.filter(composite__endswith=mount_id, signal_type__in = signal_type, domain = domain)
        except:
            return Response({'data':[], 'message': 'No threshold data found for this endpoint'},status=status.HTTP_404_NOT_FOUND)
        try:
            acceleration_list = {}
            velocity_list = {}
            temp_list = {}
            # thresholdDataserializer = serializers.ThresholdValuesSerializer(thresholdData)
            # jsondata = json.loads(json.dumps(thresholdDataserializer.data))
            for row in thresholdData.filter(axis=dataAxis).values():
                if row.get('signal_type') == 'acceleration':
                    acceleration_list.update({"rms_amp_level_1": row.get('rms_amp_level_1'), "rms_amp_level_2": row.get('rms_amp_level_2'), "rms_amp_level_3": row.get('rms_amp_level_3')})
                if row.get("signal_type") == 'velocity':
                    velocity_list.update({"rms_amp_level_1": row.get('rms_amp_level_1'), "rms_amp_level_2": row.get('rms_amp_level_2'), "rms_amp_level_3": row.get('rms_amp_level_3')})
                # if row.get("signal_type") == 'temp':
                    # temp_list.update({"temp_amp_level_1": row.get('temp_amp_level_1'), "temp_amp_level_2": row.get('temp_amp_level_2'), "temp_amp_level_3": row.get('temp_amp_level_3')})
                # thresholdDict.update({"amp_level_1": getattr(row, statFunc+'_level_1')})
                # thresholdDict.update({"amp_level_2": getattr(row, statFunc+'_level_2')})
                # thresholdDict.update({"amp_level_3": getattr(row, statFunc+'_level_3')})

            for temp_row in thresholdData.filter(axis='temp').values():
                if temp_row.get("signal_type") == 'temp':
                    temp_list.update({"temp_amp_level_1": temp_row.get('temp_amp_level_1'), "temp_amp_level_2": temp_row.get('temp_amp_level_2'), "temp_amp_level_3": temp_row.get('temp_amp_level_3')})

            thresholdDict.update({"acceleration": acceleration_list, "velocity": velocity_list, "temp": temp_list})
            return Response({'data':thresholdDict, 'status_code': 200}, status=status.HTTP_200_OK) 
        except:
            return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
    except:
        return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
def GetBearingFaultFrequenciesData(request):
    try:
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        composite = data.get("composite_id")
        dataTimestamp = data.get("timestamp")
        signal_type = data.get("signal_type")
        axis = data.get("axis")
        final_data = {}
        max_value = data.get("max_value")
        # bff = data.get("bff")
        # ls = []
        # for i,j in bff.items():
        #     if j==True:
        #         ls.append(i+'_amp')
        #         ls.append(i+'_freq') 
        if dataTimestamp:
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
        try:
            # frequencyData = models.BearingFaultFrequenciesMaster.objects.get(composite=composite, timestamp=local_dt, axis=axis, signal_type=signal_type)
            frequencyData = models.BearingFaultFrequenciesMaster.objects.filter(composite=composite, timestamp=local_dt, axis=axis, signal_type=signal_type).order_by('-timestamp')[0]
        except:
            return Response({'message':"Bearing fault frequency data not calculated for selected spectrum."},status=status.HTTP_404_NOT_FOUND)
        
        bff_data = serializers.BearingFaultFrequenciesMasterSerializer(frequencyData)
        df = json.loads(json.dumps(bff_data.data))
        frequencyList = ['bpfo','bpfi','bsf','ftf']
        for frequency in frequencyList:
            if len(df.get(frequency+"_amp"))>0 and len(df.get(frequency+"_freq"))>0:
                faultList = []
                for i in range(0,5):
                    faultList.append(float(df.get(frequency+"_freq")[i]))
                    # faultList.append([float(df.get(frequency+"_freq")[i]), float(df.get(frequency+"_amp")[i])])
                final_data.update({frequency:faultList})
                flag =  True
                message = "Data found"
                api_status = status.HTTP_200_OK
                # return Response({"data": final_data, "flag": flag},  status=status.HTTP_200_OK)
            else:
                final_data.update({frequency:[]})
                flag =  False
                message = "Bearing fault frequency data not calculated for selected spectrum."
                api_status = status.HTTP_404_NOT_FOUND

        return Response({"data": final_data, "flag": flag, 'message':message},  status = api_status)
        # final_data = {}
        # if len(ls) > 0:
        #     for k in ls:
        #         final_data.update({k: df.get(k)})
        # else:
        #     final_data = {"message": "No fault frequency selected."}
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def getEndpointDetailsReport(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            asset_data_list = data.get("asset_id")
            asset_id_list = [i.get("id") for i in asset_data_list]
            linked_list = [True, False]
            final_data = []
            deviceData = models.DeviceMountMaster.objects.filter(asset_id__in = asset_id_list, is_linked__in = linked_list).order_by('id')
            deviceDataSerializer = serializers.DeviceMountMasterSerializer(deviceData, many=True)
            deviceDataSerializerData = json.loads(json.dumps(deviceDataSerializer.data))
            for i in deviceDataSerializerData:
                    for j in asset_data_list:
                        if i.get("asset_id") == j.get("id"):
                            i["asset_name"] = j.get("asset_name")
            return Response({"data":deviceDataSerializerData}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)






# @api_view(['POST'])
# def getEndpointDataReport(request):
#     try:
#         if request.method == 'POST':
#             data = JSONParser().parse(request)
#             if not data:
#                 return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
#             latestDataKeys = data.get("composite_keys_latest")
#             timeDataKeys = data.get("composite_keys_timestamp")

#             # """ Getting data against latest timestamp """
#             latest_composite_id_list = [i.get("composite_id") for i in latestDataKeys]
#             linked_list = [True, False]
#             final_data_latest = []
#             deviceData = models.DeviceMountMaster.objects.filter(composite_id__in = latest_composite_id_list, is_linked__in = linked_list).order_by('id')
#             if len(deviceData) > 0:
#                 for single_device in deviceData:
#                     mount_id = single_device.id
#                     serial_data = serializers.DeviceMountMasterSerializer(single_device)
#                     single_device_data = json.loads(json.dumps(serial_data.data))
#                     composite_id = single_device.composite_id
#                     asset_id = single_device_data.get('asset_id')

#                     try:
#                         laterstTimeStampAcc = models.AccelerationStatTimeMaster.objects.filter(asset_id=asset_id, composite__endswith=mount_id).latest('timestamp')
#                         if laterstTimeStampAcc:
#                             acc_stat_data = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id, timestamp=laterstTimeStampAcc.timestamp)
#                             acc_data_dict = {}
#                             for accRMS in acc_stat_data:
#                                 acc_data_dict.update({accRMS.axis:{"timestamp":int(parser.isoparse(str(accRMS.timestamp)).timestamp()), "rms":accRMS.rms}})
#                             single_device_data.update({"acceleration":acc_data_dict})
#                     except:
#                         dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
#                         single_device_data.update({"acceleration":dummyData})
                    
#                     try:
#                         laterstTimeStampVel = models.VelocityStatTimeMaster.objects.filter(asset_id=asset_id, composite__endswith=mount_id).latest('timestamp')
#                         if laterstTimeStampVel:
#                             vel_stat_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, timestamp=laterstTimeStampVel.timestamp)
#                             vel_data_dict = {}
#                             for velRMS in vel_stat_data:
#                                 vel_data_dict.update({velRMS.axis:{"timestamp":int(parser.isoparse(str(velRMS.timestamp)).timestamp()), "rms":velRMS.rms}})
#                             single_device_data.update({"velocity":vel_data_dict})
#                     except:
#                         dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
#                         single_device_data.update({"velocity":dummyData})
#                     final_data_latest.append(single_device_data)
#                 for i in final_data_latest:
#                     for j in latestDataKeys:
#                         if i.get("composite_id") == j.get("composite_id"):
#                             i["asset_name"] = j.get("asset_name")
#             else:
#                 final_data_latest = []


#             if len(timeDataKeys) > 0:
#                 # """ Getting data against given timestamp """
#                 timestamp_composite_id_list = [i.get("composite_id") for i in timeDataKeys]
#                 linked_list = [True, False]
#                 final_data_timestamp = []
#                 deviceData = models.DeviceMountMaster.objects.filter(composite_id__in = timestamp_composite_id_list, is_linked__in = linked_list).order_by('id')
#                 if len(deviceData) > 0:
#                     for single_device in deviceData:
#                         mount_id = single_device.id
#                         serial_data = serializers.DeviceMountMasterSerializer(single_device)
#                         single_device_data = json.loads(json.dumps(serial_data.data))
#                         composite_id = single_device.composite_id
#                         for i in timeDataKeys:
#                             if i.get("composite_id") == composite_id:
#                                 timestamp_value = i.get("timestamp")
#                         try:
#                             utc_dt = datetime.utcfromtimestamp(int(timestamp_value)).replace(tzinfo=pytz.utc)
#                             local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
#                         except:
#                             return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
#                         try:
#                             acc_stat_data = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id, timestamp=local_dt)
#                             acc_data_dict = {}
#                             for accRMS in acc_stat_data:
#                                 acc_data_dict.update({accRMS.axis:{"timestamp":int(parser.isoparse(str(accRMS.timestamp)).timestamp()), "rms":accRMS.rms}})
#                             single_device_data.update({"acceleration":acc_data_dict})
#                         except:
#                             dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
#                             single_device_data.update({"acceleration":dummyData})
                        
#                         try:
#                             vel_stat_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, timestamp=local_dt)
#                             vel_data_dict = {}
#                             for velRMS in vel_stat_data:
#                                 vel_data_dict.update({velRMS.axis:{"timestamp":int(parser.isoparse(str(velRMS.timestamp)).timestamp()), "rms":velRMS.rms}})
#                             single_device_data.update({"velocity":vel_data_dict})
#                         except:
#                             dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
#                             single_device_data.update({"velocity":dummyData})
#                         final_data_timestamp.append(single_device_data)
#                     for i in final_data_timestamp:
#                         for j in timeDataKeys:
#                             if i.get("composite_id") == j.get("composite_id"):
#                                 i["asset_name"] = j.get("asset_name")

#                 else:
#                     final_data_timestamp = []
#             else:
#                 final_data_timestamp = []

#             final_data = final_data_latest + final_data_timestamp
#             return Response({"data":final_data}, status=status.HTTP_200_OK)
#     except:
#         return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
def getEndpointDataReport(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            latestDataKeys = data.get("composite_keys_latest")
            timeDataKeys = data.get("composite_keys_timestamp")

            # """ Getting data against latest timestamp """
            latest_composite_id_list = [i.get("composite_id") for i in latestDataKeys]
            linked_list = [True, False]
            final_data_latest = []
            deviceData = models.DeviceMountMaster.objects.filter(composite_id__in = latest_composite_id_list, is_linked__in = linked_list).order_by('id')
            if len(deviceData) > 0:
                for single_device in deviceData:
                    mount_id = single_device.id
                    serial_data = serializers.DeviceMountMasterSerializer(single_device)
                    single_device_data = json.loads(json.dumps(serial_data.data))
                    composite_id = single_device.composite_id
                    asset_id = single_device_data.get('asset_id')

                    try:
                        acc_stat_data = models.AccelerationStatTimeOptimized.objects.filter(mount_id=mount_id).latest('timestamp')
                        if acc_stat_data:
                            acc_data_dict = {}
                            acc_data_dict.update({
                                'Axial':{"timestamp":int(parser.isoparse(str(acc_stat_data.timestamp)).timestamp()), "rms": round(acc_stat_data.rms_Axial, 2)},
                                'Vertical':{"timestamp":int(parser.isoparse(str(acc_stat_data.timestamp)).timestamp()), "rms": round(acc_stat_data.rms_Vertical, 2)},
                                'Horizontal':{"timestamp":int(parser.isoparse(str(acc_stat_data.timestamp)).timestamp()), "rms": round(acc_stat_data.rms_Horizontal, 2)},
                                })
                            single_device_data.update({"acceleration":acc_data_dict})

                    except:
                        dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
                        single_device_data.update({"acceleration":dummyData})
                    
                    try:
                        vel_stat_data = models.VelocityStatTimeOptimized.objects.filter(mount_id=mount_id).latest('timestamp')
                        if vel_stat_data:
                            vel_data_dict = {}
                            vel_data_dict.update({
                                'Axial':{"timestamp":int(parser.isoparse(str(vel_stat_data.timestamp)).timestamp()), "rms": round(vel_stat_data.rms_Axial, 2)},
                                'Vertical':{"timestamp":int(parser.isoparse(str(vel_stat_data.timestamp)).timestamp()), "rms": round(vel_stat_data.rms_Vertical, 2)},
                                'Horizontal':{"timestamp":int(parser.isoparse(str(vel_stat_data.timestamp)).timestamp()), "rms": round(vel_stat_data.rms_Horizontal, 2)},
                                })
                            single_device_data.update({"velocity":vel_data_dict})

                    except:
                        dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
                        single_device_data.update({"velocity":dummyData})

                    final_data_latest.append(single_device_data)
                for i in final_data_latest:
                    for j in latestDataKeys:
                        if i.get("composite_id") == j.get("composite_id"):
                            i["asset_name"] = j.get("asset_name")
            else:
                final_data_latest = []


            if len(timeDataKeys) > 0:
                # """ Getting data against given timestamp """
                timestamp_composite_id_list = [i.get("composite_id") for i in timeDataKeys]
                linked_list = [True, False]
                final_data_timestamp = []
                deviceData = models.DeviceMountMaster.objects.filter(composite_id__in = timestamp_composite_id_list, is_linked__in = linked_list).order_by('id')
                if len(deviceData) > 0:
                    for single_device in deviceData:
                        mount_id = single_device.id
                        serial_data = serializers.DeviceMountMasterSerializer(single_device)
                        single_device_data = json.loads(json.dumps(serial_data.data))
                        composite_id = single_device.composite_id
                        for i in timeDataKeys:
                            if i.get("composite_id") == composite_id:
                                timestamp_value = i.get("timestamp")
                        try:
                            utc_dt = datetime.utcfromtimestamp(int(timestamp_value)).replace(tzinfo=pytz.utc)
                            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                        except:
                            return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)

                        try:
                            acc_stat_data = models.AccelerationStatTimeOptimized.objects.get(mount_id=mount_id, timestamp=local_dt)
                            if acc_stat_data:
                                acc_data_dict = {}
                                acc_data_dict.update({
                                    'Axial':{"timestamp":int(parser.isoparse(str(acc_stat_data.timestamp)).timestamp()), "rms": round(acc_stat_data.rms_Axial, 2)},
                                    'Vertical':{"timestamp":int(parser.isoparse(str(acc_stat_data.timestamp)).timestamp()), "rms": round(acc_stat_data.rms_Vertical, 2)},
                                    'Horizontal':{"timestamp":int(parser.isoparse(str(acc_stat_data.timestamp)).timestamp()), "rms": round(acc_stat_data.rms_Horizontal, 2)},
                                    })
                                single_device_data.update({"acceleration":acc_data_dict})

                        except Exception as e1:
                            print("exception in acc", mount_id, "------------", e1)
                            dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
                            single_device_data.update({"acceleration":dummyData})
                        
                        try:
                            vel_stat_data = models.VelocityStatTimeOptimized.objects.get(mount_id=mount_id, timestamp=local_dt)
                            if vel_stat_data:
                                vel_data_dict = {}
                                vel_data_dict.update({
                                    'Axial':{"timestamp":int(parser.isoparse(str(vel_stat_data.timestamp)).timestamp()), "rms": round(vel_stat_data.rms_Axial, 2)},
                                    'Vertical':{"timestamp":int(parser.isoparse(str(vel_stat_data.timestamp)).timestamp()), "rms": round(vel_stat_data.rms_Vertical, 2)},
                                    'Horizontal':{"timestamp":int(parser.isoparse(str(vel_stat_data.timestamp)).timestamp()), "rms": round(vel_stat_data.rms_Horizontal, 2)},
                                    })
                                single_device_data.update({"velocity":vel_data_dict})

                        except Exception as e2:
                            print("exception in vel", mount_id, "------------", e2)
                            dummyData = {"Axial":{"timestamp":"-","rms":"-"},"Vertical":{"timestamp":"-","rms":"-"},"Horizontal":{"timestamp":"-","rms":"-"}}
                            single_device_data.update({"velocity":dummyData})
                        
                        final_data_timestamp.append(single_device_data)
                    for i in final_data_timestamp:
                        for j in timeDataKeys:
                            if i.get("composite_id") == j.get("composite_id"):
                                i["asset_name"] = j.get("asset_name")

                else:
                    final_data_timestamp = []
            else:
                final_data_timestamp = []
            final_data = final_data_latest + final_data_timestamp
            return Response({"data":final_data}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def getWaterfallData(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            composite_id = data.get("composite_id")
            dataTimestamp = data.get("timestamp")
            dataAxis = data.get("axis")
            signal_type = data.get("signal_type")

            try:
                device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_id)
                mount_id = "_"+str(device_mount_data.id)
                # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
                # if sensor_orient_data.x == data.get("axis"):
                #     dataAxis = 'x'
                # elif sensor_orient_data.y == data.get("axis"):
                #     dataAxis = 'y'
                # elif sensor_orient_data.z == data.get("axis"):
                #     dataAxis = 'z'
                # else:
                #     return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
            except:
                return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
    
            final_data = {"composite_id": composite_id, "axis": dataAxis, "signal_type": signal_type}

            try:
                # pdb.set_trace()
                if signal_type == 'acceleration':
                    if dataTimestamp:
                        try:
                            utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                        except:
                            return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                        data.update({'timestamp':local_dt})
                        acc_data = models.AccelerationSpectrumMaster.objects.filter(composite__endswith=mount_id, axis=dataAxis, timestamp__lte=data.get("timestamp")).order_by('-timestamp')[:10]
                        final_chart_list = []
                        for i in acc_data:
                            single_chart_list = []
                            single_date = i.timestamp
                            single_data = i.data
                            single_time_stamp_data_x = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id, timestamp = single_date).values("acceleration")[0]
                            single_chart_list = [[single_time_stamp_data_x.get("acceleration")[i],     single_date.strftime("%m/%d/%Y %H:%M:%S"),     single_data[i]] for i in range(len(single_data))]
                            final_chart_list.append(single_chart_list)
                        final_data.update({"data": final_chart_list})
            except:
                return Response({'message':'Something went wrong with Acceleration Spectrum Waterfall Plot, please try after some time'}, status=status.HTTP_409_CONFLICT)
            
            try:
                if signal_type == 'velocity':
                    if dataTimestamp:
                        try:
                            utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                        except:
                            return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                        data.update({'timestamp':local_dt})
                        acc_data = models.VelocitySpectrumMaster.objects.filter(composite__endswith=mount_id, axis=dataAxis, timestamp__lte=data.get("timestamp")).order_by('-timestamp')[:10]
                        final_chart_list = []
                        for i in acc_data:
                            single_chart_list = []
                            single_date = i.timestamp
                            single_data = i.data
                            single_time_stamp_data_x = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id, timestamp = single_date).values("acceleration")[0]
                            single_chart_list = [[single_time_stamp_data_x.get("acceleration")[i],     single_date.strftime("%m/%d/%Y %H:%M:%S"),     single_data[i]] for i in range(len(single_data))]
                            final_chart_list.append(single_chart_list)
                        final_data.update({"data": final_chart_list})
            except:
                return Response({'message':'Something went wrong with Velocity Spectrum Waterfall Plot, please try after some time'}, status=status.HTTP_409_CONFLICT)

            try:
                if signal_type == 'displacement':
                    if dataTimestamp:
                        try:
                            utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                            local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                        except:
                            return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                        data.update({'timestamp':local_dt})
                        acc_data = models.DisplacementSpectrumMaster.objects.filter(composite__endswith=mount_id, axis=dataAxis, timestamp__lte=data.get("timestamp")).order_by('-timestamp')[:10]
                        final_chart_list = []
                        for i in acc_data:
                            single_chart_list = []
                            single_date = i.timestamp
                            single_data = i.data
                            single_time_stamp_data_x = models.SpectrumChartDataMaster.objects.filter(composite__endswith=mount_id, timestamp = single_date).values("acceleration")[0]
                            single_chart_list = [[single_time_stamp_data_x.get("acceleration")[i],     single_date.strftime("%m/%d/%Y %H:%M:%S"),     single_data[i]] for i in range(len(single_data))]
                            final_chart_list.append(single_chart_list)
                        final_data.update({"data": final_chart_list})
            except:
                return Response({'message':'Something went wrong with Displacement Spectrum Waterfall Plot, please try after some time'}, status=status.HTTP_409_CONFLICT)

            return Response({"data":final_data}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def getAlarmHistoryData(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            final_data = {}
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            asset_list = data.get("asset_list")
            alarmDataObject = models.AlarmHistoryMaster.objects

            addressedAlarms = alarmDataObject.filter(asset_id__in=asset_list, addressed=True).order_by('-timestamp').values()

            unAddressedAlarms = alarmDataObject.filter(asset_id__in=asset_list, addressed=False).order_by('-timestamp').values()

            processedAddressedAlarms = [
                {
                    "addressed": i.get('addressed'), "asset_id": i.get("asset_id"),\
                    "axis": i.get("axis").capitalize(), "composite": i.get("composite"), "id": i.get("id"), "observed_value": i.get("observed_value"),\
                    "priority": i.get("priority"), "sensor_location": i.get("sensor_location"), "signal_type": i.get("signal_type").capitalize(),\
                    "threshold_value": i.get("threshold_value"), "timestamp": i.get('timestamp').replace(tzinfo=pytz.utc).astimezone(local_tz).strftime('%Y-%m-%d %H:%M'),\
                    "trend_type": ' '.join(i.get("trend_type").split("_")[:-1]).capitalize(), "timestamp_for_trend": i.get('timestamp').timestamp()
                    } 
                for i in addressedAlarms
                ]
            
            processedUnaddressedAlarms = [
                {
                    "addressed": i.get('addressed'), "asset_id": i.get("asset_id"),\
                    "axis": i.get("axis").capitalize(), "composite": i.get("composite"), "id": i.get("id"), "observed_value": i.get("observed_value"),\
                    "priority": i.get("priority"), "sensor_location": i.get("sensor_location"), "signal_type": i.get("signal_type").capitalize(),\
                    "threshold_value": i.get("threshold_value"), "timestamp": i.get('timestamp').replace(tzinfo=pytz.utc).astimezone(local_tz).strftime('%Y-%m-%d %H:%M'),\
                    "trend_type": ' '.join(i.get("trend_type").split("_")[:-1]).capitalize(), "timestamp_for_trend": i.get('timestamp').timestamp()
                    } 
                for i in unAddressedAlarms
                ]


            final_data.update({"addressedAlarms":processedAddressedAlarms})
            final_data.update({"unAddressedAlarms":processedUnaddressedAlarms})

            return Response(final_data, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
def getAlarmHistorySummary(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            final_data = {}
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            asset_list = data.get("asset_list")
            alarmDataObject = models.AlarmHistoryMaster.objects
            

            monthlyCount = alarmDataObject.filter(asset_id__in=asset_list).annotate(month=Trunc('timestamp', 'month', output_field=DateField())).values('month').annotate(alarms=Count('id'))
            if len(monthlyCount) > 0:
                countList = [row for row in monthlyCount]
                countList.sort(key = lambda x: datetime.strptime(str(x['month']), '%Y-%m-%d'))
                sortedList = []
                for i in countList:
                    sortedList.append({"month":i.get("month").strftime("%B-%Y"), "count":i.get("alarms")})
                final_data.update({"monthlyCount": sortedList})


                # Get the earliest and latest dates for calculations
                earliest_date = alarmDataObject.earliest('timestamp').timestamp.strftime("%Y-%m-%d")
                latest_date = datetime.now().date().strftime("%Y-%m-%d")

                # Generate a range of months from the earliest date to the latest date
                months = []
                month = datetime.strptime(earliest_date, '%Y-%m-%d').replace(day=1)
                while month <= datetime.strptime(latest_date, '%Y-%m-%d').replace(day=1):
                    months.append(month.strftime('%Y-%m-%d'))
                    month = (month.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)

                monthlyCountPriority = alarmDataObject.filter(asset_id__in=asset_list).annotate(month=Trunc('timestamp', 'month', output_field=DateField())).values('month', 'priority').annotate(count=Count('id')).order_by("month")
                
                
                # Generate a list of all possible month-category combinations
                categories = alarmDataObject.values_list('priority', flat=True).distinct()
                month_categories = list(product(months, categories))


                # Fill in any missing data with a count of 0
                filled_counts = {}
                for month, category in month_categories:
                    count = monthlyCountPriority.filter(month=month, priority=category).first()
                    if count is None:
                        filled_counts[(month, category)] = 0
                    else:
                        filled_counts[(month, category)] = count['count']


                # Create a list of series data in ECharts format
                series = []
                for category in categories:
                    data = []
                    for month in months:
                        count = filled_counts[(month, category)]
                        data.append(count)
                    series.append({
                        'name': category,
                        'type': 'line',
                        'data': data,
                        'smooth': 'true'
                    })
                month_string = [datetime.strptime(date_str, '%Y-%m-%d').date() for date_str in months]
                dmonth_string_formatted = [date.strftime('%B-%y') for date in month_string]
                final_data.update({"series": series, "timestamp":dmonth_string_formatted})
                return Response(final_data, status=status.HTTP_200_OK)
            else:
                return Response({'No data found for selected asset.'}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def getAlarmDiagnosticReports(request):
    try:
        data = JSONParser().parse(request)
        alarm_id = data.get("alarm_id")
        alarm_source = data.get("alarm_source", "alarm_history")

        if not alarm_id:
            return Response({'message': 'alarm_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if alarm_source not in ["alarm_history", "alarm_queue"]:
            return Response({'message': 'alarm_source must be "alarm_history" or "alarm_queue"'}, status=status.HTTP_400_BAD_REQUEST)

        filters = {"alarm_history_id": alarm_id} if alarm_source == "alarm_history" else {"alarm_queue_id": alarm_id}
        reports = (
            models.AssetDiagnosticReportMaster.objects
            .filter(**filters)
            .order_by("-created_at", "-id")
            .values(
                "id",
                "asset_id",
                "trigger_source",
                "response_json",
                "result",
                "status",
                "error_message",
                "created_at",
                "updated_at",
            )
        )

        report_list = []
        for report in reports:
            if report.get("created_at"):
                report["created_at"] = report["created_at"].astimezone(local_tz).strftime('%Y-%m-%d %H:%M')
            if report.get("updated_at"):
                report["updated_at"] = report["updated_at"].astimezone(local_tz).strftime('%Y-%m-%d %H:%M')
            report_list.append(report)

        return Response(
            {
                "message": "Success",
                "alarm_id": alarm_id,
                "alarm_source": alarm_source,
                "diagnostic_reports": report_list,
                "totalCount": len(report_list),
            },
            status=status.HTTP_200_OK,
        )

    except Exception:
        return Response(
            {'message': 'Something went wrong, please try after sometime'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def getAssetHealthKPISummary(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            org_id = data.get("org_id")
            asset_list = data.get("asset_list")
            final_data = {"org_id": org_id, "Critical": 0, "Danger": 0, "Alert": 0, "Healthy": 0, "Not Defined": 0, "health_breakup_percentage": []}
            try:
                totalAssetsMonitored = models.DeviceMountMaster.objects.filter(asset_id__in=asset_list, org_id=org_id)
                assetCount = totalAssetsMonitored.count()
                final_data.update({"total_live_sensors": assetCount})
                # totalLiveSensors = totalAssetsMonitored.values('asset_id').distinct().count()
                # final_data.update({"total_assets_monitored": totalLiveSensors})
            except:
                final_data.update({"total_live_sensors": "-"})
                # final_data.update({"total_assets_monitored": "-"})
                return Response({"data":final_data, "message": "Something went wrong while counting assets."}, status=status.HTTP_404_NOT_FOUND)
            
            try:
                counts = models.AssetHealthMaster.objects.filter(asset_id__in=asset_list).values('status').annotate(count=Count('id'))
                # countList = [{'status': 'Critical', 'count': 0}, {'status': 'Danger', 'count': 0}, {'status': 'Alert', 'count': 0}, {'status': 'Healthy', 'count': 0}, {'status': 'Not Defined', 'count': 0}]
                total_count = 0
                for i in counts:
                    if i.get("status") == "Critical":
                        total_count += i.get("count")
                        final_data.update({"Critical": i.get("count")})
                    elif i.get("status") == "Danger":
                        total_count += i.get("count")
                        final_data.update({"Danger": i.get("count")})
                    elif i.get("status") == "Alert":
                        total_count += i.get("count")
                        final_data.update({"Alert": i.get("count")})
                    elif i.get("status") == "Healthy":
                        total_count += i.get("count")
                        final_data.update({"Healthy": i.get("count")})
                    elif i.get("status") == "Not Defined":
                        total_count += i.get("count")
                        final_data.update({"Not Defined": i.get("count")})
                    else:
                        pass

                statusList = ["Critical", "Danger", "Alert", "Healthy", "Not Defined"]
                for i in statusList:
                    final_data.get("health_breakup_percentage").append({"name":i, "value": final_data.get(i)})

                
            except:
                pass
            try:
                openAlarms = models.AlarmHistoryMaster.objects.filter(asset_id__in=asset_list, addressed=False).count()
                final_data.update({"openAlarms": openAlarms})
            except:
                final_data.update({"openAlarms": "-"})
            return Response({"data":final_data}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
    




@api_view(['POST', 'PATCH'])
def AssetHealthAPI(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            org_id = data.get("org_id")
            asset_id_list = data.get("asset_id")
            asset_status = data.get("asset_status")
            # pdb.set_trace()
            for asset_id in asset_id_list:
                existingAssetHealth = models.AssetHealthMaster.objects.filter(asset_id=asset_id)
                if len(existingAssetHealth) == 0:
                    asset_data = {"asset_id": asset_id, "org_id": org_id, "status": asset_status}
                    healthSerializerData = serializers.AssetHealthMasterSerializer(data=asset_data)
                    healthHistorySerializerData = serializers.AssetHealthHistoryMasterSerializer(data=asset_data)
                    if healthSerializerData.is_valid():
                        if healthHistorySerializerData.is_valid():
                            healthSerializerData.save()
                            healthHistorySerializerData.save()
                            return Response({"data":asset_data}, status=status.HTTP_200_OK)
                        return Response({'message':get_error_msg(healthHistorySerializerData.errors)}, status=status.HTTP_400_BAD_REQUEST)
                    return Response({'message':get_error_msg(healthSerializerData.errors)}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    pass
                    
            return Response({"data":asset_data}, status=status.HTTP_200_OK)



            # totalAssetsMonitored = models.DeviceMountMaster.objects.filter(asset_id__in=asset_list, org_id=org_id).exclude(mac_id=None)
            # assetCount = totalAssetsMonitored.count()
            # final_data.update({"total_live_sensors": assetCount})
            # totalLiveSensors = totalAssetsMonitored.values('asset_id').distinct().count()
            # final_data.update({"total_assets_monitored": totalLiveSensors})

        elif request.method == 'PATCH':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            asset_id = data.get("asset_id")
            alarm_id = data.get("alarm_id")
            asset_status = data.get("asset_status")
            org_id = data.get("org_id")
            if alarm_id:
                existingAlarmData = models.AlarmHistoryMaster.objects.get(id=alarm_id)
                existingAlarmData.addressed = True
                existingAlarmData.save()
            
            currentDate = datetime.now().date()
            try:
                existingAssetData = models.AssetHealthMaster.objects.get(asset_id=asset_id)
                existingAssetData.status = asset_status
                existingAssetData.save()
            except:
                asset_data = {"asset_id": asset_id, "org_id": org_id, "status": asset_status}
                healthSerializerData = serializers.AssetHealthMasterSerializer(data=asset_data)
                if healthSerializerData.is_valid():
                    healthSerializerData.save()

            selectedAssetHealthHistory = models.AssetHealthHistoryMaster.objects.filter(asset_id=asset_id, creation_date=currentDate)
            if len(list(selectedAssetHealthHistory)) > 0:
                for item in selectedAssetHealthHistory:
                    item.status = asset_status
                    item.save()
            else:
                asset_health_history_data = {"asset_id": asset_id, "org_id": org_id, "status": asset_status} 
                assetHealthHistorySerializer = serializers.AssetHealthHistoryMasterSerializer(data=asset_health_history_data)
                if assetHealthHistorySerializer.is_valid():
                    assetHealthHistorySerializer.save()

            return Response({"data":"Data updated successfully"}, status=status.HTTP_200_OK)

    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
    
@api_view(['GET','POST'])
def getAssetHealthHistory(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            asset_list = data.get("asset_list")
            groupLogic = data.get("group_by")
            final_data = {}

            # /////////////////// Month dates list (common for both logics monthly/weekly) ///////////////////
            # get list of last day of last N months
            now = datetime.now()
            current_year = now.year
            current_month = now.month
            month_end_dates = []
            for i in range(4):  # make dynamic as per select number of months
                last_day = calendar.monthrange(current_year, current_month)[1]
                month_end_date = datetime(current_year, current_month, last_day)
                month_end_dates.append(month_end_date)
                current_month -= 1
                if current_month == 0:
                    current_month = 12
                    current_year -= 1
            month_end_dates.reverse()
            # //////////////////////////////////// monthly logic ////////////////////////////////////
            if groupLogic == 'month':
                combined_list = []
                for single_month in month_end_dates:
                    month_stamp = single_month.month


                    # for single_asset in asset_list:
                    #     asset_month_data = models.AssetHealthHistoryMaster.objects.filter(asset_id=single_asset, creation_date__month=month_stamp)
                    #     if len(asset_month_data) > 0:
                    #         latest_date_data = asset_month_data.latest('creation_date')
                    #         dct = {"status": latest_date_data.status, "timestamp": latest_date_data.creation_date.strftime("%b-%Y")}
                    #         combined_list.append(dct)


                    # pdb.set_trace()
                    latest_dates = models.AssetHealthHistoryMaster.objects.filter(
                                        asset_id__in=asset_list, 
                                        creation_date__month=month_stamp
                                    ).values('asset_id').annotate(
                                        latest_date=Max('creation_date')
                                    )

                    # Convert the result into a dictionary for easy access
                    latest_dates_dict = {item['asset_id']: item['latest_date'] for item in latest_dates}

                    # combined_list = []
                    for asset_id, latest_date in latest_dates_dict.items():
                        latest_asset_data = models.AssetHealthHistoryMaster.objects.filter(
                            asset_id=asset_id, 
                            creation_date=latest_date
                        ).order_by('-creation_date')[0]

                        dct = {
                            "status": latest_asset_data.status, 
                            "timestamp": latest_asset_data.creation_date.strftime("%b-%Y")
                        }
                        combined_list.append(dct)


            # //////////////////////////////////// weekly logic ////////////////////////////////////
            if groupLogic == 'week':
                intervals = []
                for single_month in month_end_dates:
                    # Compute the number of complete weeks and remaining days
                    num_days = single_month.day
                    num_weeks = num_days // 7
                    remaining_days = num_days % 7

                    # Create a list of the interval start and end dates
                    start_date = single_month.replace(day=1)
                    for i in range(num_weeks-1):
                        end_date = start_date + timedelta(days=6)
                        intervals.append((start_date, end_date))
                        start_date = end_date + timedelta(days=1)

                    # Add the final interval with the remaining days
                    end_date = start_date + timedelta(days=remaining_days) + timedelta(days=6)
                    intervals.append((start_date, end_date))

                combined_list = []
                for single_date_range in intervals:
                    start_date_range = single_date_range[0]
                    end_date_range = single_date_range[1]

                    # for single_asset in asset_list:
                    #     asset_month_data = models.AssetHealthHistoryMaster.objects.filter(asset_id=single_asset, creation_date__range=[start_date_range, end_date_range])
                    #     if len(asset_month_data) > 0:
                    #         latest_date_data = asset_month_data.latest('creation_date')
                    #         dct = {"status": latest_date_data.status, "timestamp": start_date_range.strftime("%d") + "-" + end_date_range.strftime("%d %b")}
                    #         combined_list.append(dct)


                    latest_dates = models.AssetHealthHistoryMaster.objects.filter(
                        asset_id__in=asset_list, 
                        creation_date__range=[start_date_range, end_date_range]
                    ).values('asset_id').annotate(
                        latest_date=Max('creation_date')
                    )

                    # Convert the result into a dictionary for easy access
                    latest_dates_dict = {item['asset_id']: item['latest_date'] for item in latest_dates}

                    for asset_id, latest_date in latest_dates_dict.items():
                        latest_asset_data = models.AssetHealthHistoryMaster.objects.filter(
                            asset_id=asset_id, 
                            creation_date=latest_date
                        ).order_by('-creation_date')[0]

                        dct = {
                            "status": latest_asset_data.status, 
                            "timestamp": start_date_range.strftime("%d") + "-" + end_date_range.strftime("%d %b")
                        }
                        combined_list.append(dct)




            # List of status types to count
            status_types = ['Not Defined', 'Alert', 'Healthy', 'Danger', 'Critical']
            counts = defaultdict(lambda: {status_type: 0 for status_type in status_types})

            for item in combined_list:
                month = item.get('timestamp')
                counts[month][item['status']] += 1
            series = [
                {
                    "name": "Healthy",
                    "type": "bar",
                    "data": [],
                    "barWidth": 15
                },
                {
                    "name": "Alert",
                    "type": "bar",
                    "data": [],
                    "barWidth": 15
                },
                {
                    "name": "Danger",
                    "type": "bar",
                    "data": [],
                    "barWidth": 15
                },
                {
                    "name": "Critical",
                    "type": "bar",
                    "data": [],
                    "barWidth": 15
                }
            ]
            month_categories = []
            for i, j in counts.items():
                month_categories.append(i)
                series[0].get("data").append(j.get("Healthy"))
                series[1].get("data").append(j.get("Alert"))
                series[2].get("data").append(j.get("Danger"))
                series[3].get("data").append(j.get("Critical"))
            final_data = {}
            final_data.update({"series": series, "timestamp": month_categories})
            return Response({"data": final_data}, status=status.HTTP_200_OK)

        elif request.method == 'GET':
            # pdb.set_trace()
            assetHealthHistory = models.AssetHealthHistoryMaster.objects.all()
            serialData = serializers.AssetHealthHistoryMasterSerializerAll(assetHealthHistory, many=True)
            return Response({"data": serialData.data}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
    


@api_view(['POST'])
def getAssetHealthStatus(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            asset_list = data.get("asset_list")
            org_id = data.get("org_id")
            t1 = datetime.now()
            assetHealthData = models.AssetHealthMaster.objects.filter(asset_id__in=asset_list, org_id=org_id).values('asset_id').annotate(asset_status=F('status'))
            t2 = datetime.now()
            print("AssetHealthMaster", t2-t1)
            # if len(assetHealthData) > 0:
            #     t3=datetime.now()
            #     latest_records = models.TemperatureMaster.objects.filter(asset_id__in=asset_list).values('asset_id').annotate(last_data=Max('timestamp'))
            #     t4 = datetime.now()
            #     print("TemperatureMaster", t4-t3)
            #     latest_records_list = list(latest_records)
            #     timestamp_dict = {item['asset_id']: item['last_data'] for item in latest_records_list}
            #     t5 = datetime.now()
            #     updated_queryset = assetHealthData.annotate(
            #         last_data=Case(
            #             *[When(asset_id=key, then=Value(value.timestamp(), output_field=IntegerField())) for key, value in timestamp_dict.items()],
            #             default=Value(0, output_field=IntegerField()),
            #             output_field=IntegerField(),
            #         )
            #     )
            #     t6 = datetime.now()
            #     print("list update query", t6-t5)
            return Response({"data": assetHealthData}, status=status.HTTP_200_OK) 
            # else:
                # return Response({"data": "No asset health data found for seleted assets."}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def getSingleAssetHealthHistory(request):
    # pdb.set_trace()
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            asset_id = data.get("asset_id")
            final_data = {}
            try:
            #################### Current health status ####################
                assetHealth = models.AssetHealthMaster.objects.get(asset_id=asset_id)
                final_data.update({"assetHealth": assetHealth.status, "assetScore": assetHealth.score})
            except:
                final_data.update({"assetHealth": "NA"})

            try:
                #################### History data ####################
                assetData = models.AssetHealthHistoryMaster.objects.filter(asset_id=asset_id).values('creation_date', 'status').order_by('-creation_date')[:65]
                # statuses = ['Not Defined','Healthy','Alert','Danger','Critical']
                reversedAssetData = list(reversed(assetData))

                timeStamp = [i["creation_date"].strftime("%Y-%m-%d") for i in reversedAssetData]
                assetStatus = [j["status"] for j in reversedAssetData]
                final_data.update({"timeStamp": timeStamp, "assetStatus": assetStatus})
            except:
                final_data.update({"timeStamp": [], "assetStatus": []})
            
            return Response({"data": final_data}, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
def getAssetAgainstHealthStatus(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            org_id = data.get("org_id")
            health_health_list = data.get("asset_health")
            final_data = {}
            try:
            #################### Current health status ####################
                assetHealth = models.AssetHealthMaster.objects.filter(status__in=health_health_list, org_id=org_id).values("asset_id")
                assetList = [i.get("asset_id") for i in list(assetHealth)]
                final_data.update({"asset_list": assetList})
            except:
                final_data.update({"asset_list": []})
            
            return Response(final_data, status=status.HTTP_200_OK)
    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
def GetBearingFaultFrequencies(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            composite_id = data.get("composite_id")
            mount_id = composite_id.split("_")[-1]
            # pdb.set_trace()
            bearingInstance = models.BearingDetailMaster.objects.get(mount_id=mount_id)
            final_data = {"bpfo": bearingInstance.bpfo, "bpfi": bearingInstance.bpfi, "bsf": bearingInstance.bsf, "ftf": bearingInstance.ftf}
            return Response({"data": final_data}, status=status.HTTP_200_OK)

    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)




@api_view(['POST'])
def GetBearingFaultFrequenciesTrend(request):
    try:
        if request.method == 'POST':
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            composite_id = data.get("composite_id")
            mount_id = "_"+composite_id.split("_")[-1]
            trend_type = data.get("trend_type")
            fromDate = data.get('fromDate')
            toDate = data.get('toDate')
            singleDeviceData = {'_id':composite_id, "trend_type": trend_type}
            
            if (fromDate and toDate):
                newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                newIncreasedDate = newToDate + timedelta(days=1)
                axis_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, \
                timestamp__range=[fromDate.split("T")[0],newIncreasedDate]).order_by('-timestamp')
            else:
                timestamp_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id).latest('timestamp')
                axis_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, timestamp__lte=timestamp_data.timestamp).order_by('-timestamp')[:150]

            individualData = []
            timestampList = []
            
            if axis_data:
                for singleaxis in reversed(axis_data):
                    if len(getattr(singleaxis, trend_type)) == 5:
                    # if len(singleaxis.bpfo_amp) == 5:
                        # need logic to convert datetime to country specific dynamically
                        ist_date = singleaxis.timestamp
                        
                        individualData.append({
                            'timestamp':ist_date.timestamp(),\
                            'axis': singleaxis.axis,\
                            'data':{\
                                trend_type + '_one':getattr(singleaxis, trend_type)[0],\
                                trend_type + '_two':getattr(singleaxis, trend_type)[1],\
                                trend_type + '_three':getattr(singleaxis, trend_type)[2],\
                                trend_type + '_four':getattr(singleaxis, trend_type)[3],\
                                trend_type + '_five':getattr(singleaxis, trend_type)[4],\
                                }\
                            })
                        if ist_date.timestamp() not in timestampList:
                            timestampList.append(ist_date.timestamp())
            else:
                return Response({'message':'Trend Data not found'},status=status.HTTP_404_NOT_FOUND)
            
            finalRMSData = []
            for sintimestamp in timestampList:
                singleRMSData = {'timestamp':sintimestamp}
                for sinrms in individualData:
                    if sintimestamp == sinrms['timestamp']:
                        singleRMSData.update({sinrms['axis']:sinrms['data']})
                finalRMSData.append(singleRMSData)
            newFinalData = []
            for singlePoint in finalRMSData:
                if (singlePoint.keys() >= {'timestamp','Axial','Horizontal','Vertical'}):
                    newFinalData.append(singlePoint)
                else:
                    allKeysList = ['timestamp','Axial','Horizontal','Vertical']
                    absentKeys = [k for k in allKeysList if k not in list(singlePoint.keys())]
                    for i in absentKeys:
                        singlePoint.update({i: {trend_type+'_one': 'NA', trend_type+'_two': 'NA', trend_type+'_three': 'NA', trend_type+'_four': 'NA', trend_type+'_five': 'NA'}})
                    newFinalData.append(singlePoint)

            singleDeviceData.update({'bff':newFinalData})
            return Response(singleDeviceData,status=status.HTTP_200_OK)
            # return Response({'message':'Trend data not found'},status=status.HTTP_404_NOT_FOUND)

    except:
        return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetHarmonicTrend(request):
        if request.method == 'POST':
            try:
                data = JSONParser().parse(request)
                if not data:
                    return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
                
                composite_key = data.get('mac_id')
                fromDate = data.get('fromDate')
                toDate = data.get('toDate')
                signal_type = data.get('signalType')

            except:
                return Response({'message':'Something is wrong with the data. Please contact admin'}, status=status.HTTP_404_NOT_FOUND)
            
            try:
                singleDeviceData = {'_id':composite_key}
                try:
                    device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                    mount_id = "_"+str(device_mount_data.id)    # did for portable sensor as composite_id keeps on rotating
                    # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
                except:
                    return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
                
                if signal_type == 'velocity':
                    # pdb.set_trace()
                    if (fromDate and toDate):
                        axis_data = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, \
                            timestamp__range=[fromDate.split("T")[0],toDate.split("T")[0]]).order_by('-timestamp')
                    else:
                        try:
                            timestamp_data = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id).latest('timestamp')
                        except models.VelocityHarmonicsMaster.DoesNotExist:
                            return Response({'message':'Trend data not found.'},status=status.HTTP_404_NOT_FOUND)
                        axis_data = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, \
                                                                                      timestamp__lte=timestamp_data.timestamp).order_by('-timestamp')[:100]
                    individualData = []
                    timestampList = []
                    if axis_data:
                        for singleaxis in reversed(axis_data):
                            # need login to convert datetime to country specific dynamically
                            ist_date = singleaxis.timestamp
                            
                            individualData.append({
                                'timestamp':ist_date.timestamp(),\
                                'axis': singleaxis.axis,\
                                'data':{\
                                    '1x':singleaxis.one_amp,\
                                    '2x':singleaxis.two_amp,\
                                    '3x':singleaxis.three_amp,\
                                    '4x':singleaxis.four_amp,\
                                    '5x':singleaxis.five_amp\
                                    }
                                })
                            if ist_date.timestamp() not in timestampList:
                                timestampList.append(ist_date.timestamp())
                        
                    else:
                        return Response({'message': 'Trend data not found.'}, status=status.HTTP_404_NOT_FOUND)
                    
                    finalRMSData = []
                    for sintimestamp in timestampList:
                        singleRMSData = {'timestamp':sintimestamp}
                        for sinrms in individualData:
                            if sintimestamp == sinrms['timestamp']:
                                singleRMSData.update({sinrms['axis']:sinrms['data']})
                        finalRMSData.append(singleRMSData)
                    newFinalData = []
                    for singlePoint in finalRMSData:
                        if (singlePoint.keys() >= {'timestamp','Axial','Horizontal','Vertical'}):
                            newFinalData.append(singlePoint)

                    singleDeviceData.update({'trend':newFinalData})
                    return Response(singleDeviceData,status=status.HTTP_200_OK)
                        
            except:
                return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetEHNRTrend(request):
        if request.method == 'POST':
            try:
                data = JSONParser().parse(request)
                if not data:
                    return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
                
                composite_key = data.get('mac_id')
                fromDate = data.get('fromDate')
                toDate = data.get('toDate')

            except:
                return Response({'message':'Something is wrong with the data. Please contact admin'}, status=status.HTTP_404_NOT_FOUND)
            
            try:
                singleDeviceData = {'_id':composite_key}
                try:
                    device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                    mount_id = "_"+str(device_mount_data.id)    # did for portable sensor as composite_id keeps on rotating
                    # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
                except:
                    return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
                
                # pdb.set_trace()
                if (fromDate and toDate):
                    axis_data = models.FrequencyDomainFeatuers.objects.filter(composite__endswith=mount_id, \
                        timestamp__range=[fromDate.split("T")[0],toDate.split("T")[0]]).order_by('-timestamp')
                else:
                    try:
                        timestamp_data = models.FrequencyDomainFeatuers.objects.filter(composite__endswith=mount_id).latest('timestamp')
                    except models.FrequencyDomainFeatuers.DoesNotExist:
                        return Response({'message':'Trend data not found.'},status=status.HTTP_404_NOT_FOUND)
                    axis_data = models.FrequencyDomainFeatuers.objects.filter(composite__endswith=mount_id, \
                                                                                    timestamp__lte=timestamp_data.timestamp).order_by('-timestamp')[:100]
                individualData = []
                timestampList = []
                if axis_data:
                    for singleaxis in reversed(axis_data):
                        # need login to convert datetime to country specific dynamically
                        ist_date = singleaxis.timestamp
                        
                        individualData.append({
                            'timestamp':ist_date.timestamp(),\
                            'axis': singleaxis.axis,\
                            'data': singleaxis.ehnr
                            })
                        if ist_date.timestamp() not in timestampList:
                            timestampList.append(ist_date.timestamp())
                    
                else:
                    return Response({'message': 'Trend data not found.'}, status=status.HTTP_404_NOT_FOUND)
                
                finalEHNRData = []
                for sintimestamp in timestampList:
                    singleEHNRData = {'timestamp':sintimestamp}
                    for sinrms in individualData:
                        if sintimestamp == sinrms['timestamp']:
                            singleEHNRData.update({sinrms['axis']:sinrms['data']})
                    finalEHNRData.append(singleEHNRData)
                newFinalData = []
                for singlePoint in finalEHNRData:
                    if (singlePoint.keys() >= {'timestamp','Axial','Horizontal','Vertical'}):
                        newFinalData.append(singlePoint)

                singleDeviceData.update({'trend':newFinalData})
                return Response(singleDeviceData,status=status.HTTP_200_OK)
                    
            except:
                return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetAnalysisTrend(request):
        if request.method == 'POST':
            try:
                data = JSONParser().parse(request)
                if not data:
                    return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
                for payload in data:
                    mount_id = payload.get("mount_id")
                    axis = payload.get("axis")
                    trend_type = payload.get("trend_type")
                    if trend_type == 'vrms':
                        vrms_timestamp_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(vrms_timestamp_data) > 0:
                            # pdb.set_trace()
                            vrms_axis_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=vrms_timestamp_data.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "rms")
                            vrms_data = [[t.get("timestamp").timestamp()*1000, t.get("rms")] for t in vrms_axis_data]
                            payload.update({"message": "Trend data for VRMS found.", "data": vrms_data})
                        else:
                            payload.update({"message": "Trend data for VRMS not found.", "data": []})
                    
                    elif trend_type == 'arms':
                        arms_timestamp_data = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(arms_timestamp_data) > 0:
                            arms_axis_data = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=arms_timestamp_data.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "rms")
                            arms_data = [[t.get("timestamp").timestamp()*1000, t.get("rms")] for t in arms_axis_data]
                            payload.update({"message": "Trend data for ARMS found.", "data": arms_data})
                        else:
                            payload.update({"message": "Trend data for ARMS not found.", "data": []})
                    
                    elif trend_type == 'ehnr':
                        ehnr_timestamp_data = models.FrequencyDomainFeatuers.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(ehnr_timestamp_data) > 0:
                            ehnr_axis_data = models.FrequencyDomainFeatuers.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=ehnr_timestamp_data.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "ehnr")
                            ehnr_data = [[t.get("timestamp").timestamp()*1000, t.get("rms")] for t in ehnr_axis_data]
                            payload.update({"message": "Trend data for EHNR found.", "data": ehnr_data})
                        else:
                            payload.update({"message": "Trend data for EHNR not found.", "data": []})

                    elif trend_type == '1x':
                        timestamp_data_1x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(timestamp_data_1x) > 0:
                            axis_data_1x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=timestamp_data_1x.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "one_amp")
                            trendData_1x_data = [[t.get("timestamp").timestamp()*1000, t.get("one_amp")] for t in axis_data_1x]
                            payload.update({"message": "Trend data for 1X found.", "data": trendData_1x_data })
                        else:
                            payload.update({"message": "Trend data for 1X not found.", "data": []})
                    
                    elif trend_type == '2x':
                        timestamp_data_2x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(timestamp_data_2x) > 0:
                            axis_data_2x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=timestamp_data_2x.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "two_amp")
                            trendData_2x_data = [[t.get("timestamp").timestamp()*1000, t.get("two_amp")] for t in axis_data_2x]
                            payload.update({"message": "Trend data for 2X found.", "data": trendData_2x_data})
                        else:
                            payload.update({"message": "Trend data for 2X not found.", "data": []})

                    elif trend_type == '3x':
                        timestamp_data_3x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(timestamp_data_3x) > 0:
                            axis_data_3x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=timestamp_data_3x.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "three_amp")
                            timestampList_3x_data = [[t.get("timestamp").timestamp()*1000, t.get("three_amp")] for t in axis_data_3x]
                            payload.update({"message": "Trend data for 3X found.", "data": timestampList_3x_data})
                        else:
                            payload.update({"message": "Trend data for 3X not found.", "data": []})

                    elif trend_type == '4x':
                        timestamp_data_4x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(timestamp_data_4x) > 0:
                            axis_data_4x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=timestamp_data_4x.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "four_amp")
                            timestampList_4x_data = [[t.get("timestamp").timestamp()*1000, t.get("four_amp")] for t in axis_data_4x]
                            payload.update({"message": "Trend data for 4X found.", "data": timestampList_4x_data})
                        else:
                            payload.update({"message": "Trend data for 4X not found.", "data": []})

                    elif trend_type == '5x':
                        timestamp_data_5x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(timestamp_data_5x) > 0:
                            axis_data_5x = models.VelocityHarmonicsMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=timestamp_data_5x.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "five_amp")
                            timestampList_5x_data = [[t.get("timestamp").timestamp()*1000, t.get("five_amp")] for t in axis_data_5x]
                            payload.update({"message": "Trend data for 5X found.", "data": timestampList_5x_data})
                        else:
                            payload.update({"message": "Trend data for 5X not found.", "data": []})

                    elif trend_type == 'bpfo':
                        bpfo_timestamp_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(bpfo_timestamp_data) > 0:
                            bpfo_axis_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=bpfo_timestamp_data.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "bpfo_amp")
                            bpfo_timestampList_data = [[t.get("timestamp").timestamp()*1000, sum(t.get("bpfo_amp")[:3])] for t in bpfo_axis_data]
                            payload.update({"message": "Trend data for BPFO found.", "data": bpfo_timestampList_data})
                        else:
                            payload.update({"message": "Trend data for BPFO not found.", "data": []})

                    elif trend_type == 'bpfi':
                        bpfi_timestamp_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(bpfi_timestamp_data) > 0:
                            bpfi_axis_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=bpfi_timestamp_data.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "bpfi_amp")
                            bpfi_timestampList_data = [[t.get("timestamp").timestamp()*1000, sum(t.get("bpfi_amp")[:3])] for t in bpfi_axis_data]
                            payload.update({"message": "Trend data for BPFI found.", "data": bpfi_timestampList_data})
                        else:
                            payload.update({"message": "Trend data for BPFI not found.", "data": []})

                    elif trend_type == 'bsf':
                        bsf_timestamp_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(bsf_timestamp_data) > 0:
                            bsf_axis_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=bsf_timestamp_data.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "bsf_amp")
                            bsf_timestampList_data = [[t.get("timestamp").timestamp()*1000, sum(t.get("bsf_amp")[:3])] for t in bsf_axis_data]
                            payload.update({"message": "Trend data for BSF found.", "data": bsf_timestampList_data})
                        else:
                            payload.update({"message": "Trend data for BSF not found.", "data": []})

                    elif trend_type == 'ftf':
                        ftf_timestamp_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis)
                        if len(ftf_timestamp_data) > 0:
                            ftf_axis_data = models.BearingFaultFrequenciesMaster.objects.filter(composite__endswith=mount_id, axis=axis,\
                                timestamp__lte=ftf_timestamp_data.latest('timestamp').timestamp).order_by('-timestamp')[:150].values("timestamp", "ftf_amp")
                            ftf_timestampList_data = [[t.get("timestamp").timestamp()*1000, sum(t.get("ftf_amp")[:3])] for t in ftf_axis_data]
                            payload.update({"message": "Trend data for FTF found.", "data": ftf_timestampList_data})
                        else:
                            payload.update({"message": "Trend data for FTF not found.", "data": []})



                return Response({"data": data},status=status.HTTP_200_OK)


            except:
                return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)

                
@api_view(['POST'])
def GetAssetMonthlyTrend(request):
        if request.method == 'POST':
            try:
                data = JSONParser().parse(request)
                if not data:
                    return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
                asset_id = data.get("asset_id")
                statusDict = {"Critical": "1", "Danger": "2", "Alert": "3", "Healthy": "4", "Not Defined": "5"}
                now = datetime.now()
                current_year = now.year
                current_month = now.month
                month_end_dates = []
                for i in range(12):  # make dynamic as per select number of months
                    last_day = calendar.monthrange(current_year, current_month)[1]
                    month_end_date = datetime(current_year, current_month, last_day)
                    month_end_dates.append(month_end_date)
                    current_month -= 1
                    if current_month == 0:
                        break
                        # current_month = 12
                        # current_year -= 1
                assetHealthList = []
                for mnth in reversed(month_end_dates):
                    formattedDate = mnth.strftime("%Y-%m-%d")
                    assetData = models.AssetHealthHistoryMaster.objects.filter(asset_id=asset_id, creation_date__month = mnth.month)
                    if len(assetData) > 0:
                        assetDataU  = assetData.order_by("-creation_date")
                        assetHealthList.append({"date":formattedDate, "status": statusDict.get(assetDataU[0].status)})
                    else:
                        assetHealthList.append({"date":formattedDate, "status": "5"})
                data.update({"asset_health_trend": assetHealthList})
                return Response({"data": data},status=status.HTTP_200_OK)
                        
            except:
                return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
            


            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            mac_id = data.get("mac_id")
            composite_key  = data.get("composite_key")
            asset_id = data.get("asset_id")
            mount_location = data.get("mount_location")
            point_name = data.get("point_name")
            mount_id = data.get("mount_id")
            mount_direction = data.get("mount_direction")

            existingSensor = models.DeviceMountMaster.objects.filter(mac_id=mac_id)
            
            try:
                unMapObject = existingSensor.update(is_linked=False)
            except:
                pass
            existingMountData = models.DeviceMountMaster.objects.get(id=mount_id)
            if existingMountData:
                existingMountData.composite_id = composite_key
                existingMountData.mount_direction = mount_direction
                existingMountData.mount_location = mount_location
                existingMountData.is_linked = True
                existingMountData.mac_id = mac_id
                existingMountData.save()



@api_view(['POST'])
def savePortableSensorData(request):
    if request.method == 'POST':
            
        try:
            # pdb.set_trace()   
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            macID = data.get("mac_id")
            asset_id = data.get("asset_id")
            mount_id = data.get("mount_id")
            mount_direction = data.get("mount_direction")
            endpoint_name = data.get("name")
            composite_key = macID + "_" + str(asset_id) + "_" + str(mount_id)

            # //////////////////////////////// Mapping unmapping of received data ////////////////////////////////
            try:
                existingSensor = models.DeviceMountMaster.objects.filter(mac_id=macID)
                try:
                    unMapObject = existingSensor.update(is_linked=False)
                except:
                    pass
                existingMountData = models.DeviceMountMaster.objects.get(id=mount_id)
                if existingMountData:
                    existingMountData.composite_id = composite_key
                    existingMountData.mount_direction = mount_direction
                    existingMountData.is_linked = True
                    existingMountData.mac_id = macID
                    existingMountData.save()
            except:
                return Response({"message": "something went wrong with mapping"}, status=status.HTTP_404_NOT_FOUND)

            # //////////////////////////////// axis wise data processing ////////////////////////////////

            raw_data = data.get("raw_data")
            axis_counter = 0
            for single_data in raw_data:
                try:
                    try:
                        utc_dt = datetime.utcfromtimestamp(single_data.get("timestamp")).replace(tzinfo=pytz.utc)
                        local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                    except:
                        return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                    single_data.update({'timestamp':local_dt})
                    axisMapping = {"X":"x", "Y":"y", "Z":"z"}
                    
                    sensorType = macID.split("_")[0]
                    rData = single_data.get('raw_data')
                    samplingFrequency = int(float(single_data.get('fs')))
                    single_data['fs'] = samplingFrequency
                    no_of_samples = int(single_data.get("no_of_samples"))
                    temp = single_data.get("temperature")
                    axisCap = single_data.get("axis")
                    axis = axisMapping.get(axisCap)


                    try:
                        sesnorOrientData = models.SensorPositionMaster.objects.get(sensor_type=sensorType)
                        axisOrientation = sesnorOrientData.orientation.get(mount_direction).get(axis)
                    except models.SensorPositionMaster.DoesNotExist:
                        return Response({'message':'Unable to orientation data. Contact admin...'},status=status.HTTP_404_NOT_FOUND)
                
                
                    single_data.update({'asset_id':asset_id, "composite": composite_key})
                    api_message, api_status = saveData(single_data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp)
                    if api_message == "All Data Saved":
                        axis_counter += 1
                    else:
                        pass
                    # return Response({'message':api_message}, status=api_status)

                    # state, counter = saveData(single_data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp)
                    
                except:
                    pass
                
            if axis_counter == 3:
                api_message = "All Data Saved"
                api_status = status.HTTP_201_CREATED
                return Response({'message':api_message, "endpoint_name": endpoint_name}, status=api_status)
            else:
                return Response({'message':"Something went wrong in counter"}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wronga"}, status=status.HTTP_400_BAD_REQUEST)
        

@api_view(['POST'])
def GetRawData(request):
    if request.method == 'POST':
        try:
            # pdb.set_trace()
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_id = data.get("composite_id")
            axis = data.get("axis")
            finalData = {"composite": composite_id, "axis": axis}
            if axis:
                rawData = models.RawDataMaster.objects.filter(axis=axis, composite__endswith = composite_id)
            else:
                rawData = models.RawDataMaster.objects.filter(composite__endswith=composite_id)
            id_list = []
            for row in rawData:
                id_list.append(row.id)
            finalData.update({"ids": id_list})
            return Response(finalData,status=status.HTTP_200_OK)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def AccelerationEnvelopePlay(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            axis = data.get("axis")
            composite_id = data.get("composite_id")
            dataTimestamp = data.get("timestamp")
            highPass = data.get("high_pass")
            lowPass = data.get("low_pass")
            finalData = {"composite_id": composite_id, "axis": axis, "timestamp": dataTimestamp, "high_pass": highPass, "low_pass": lowPass}

            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
            try:
                # pdb.set_trace()
                rawData = models.RawDataMaster.objects.filter(axis=axis, composite=composite_id, timestamp=data.get("timestamp")).order_by('-timestamp')[0]

                raw_signal = rawData.raw_data
                raw_signal = [float(i) for i in raw_signal]
                samplingFrequency = float(rawData.fs)

                vibrationDataRawSignal = np.multiply(raw_signal, 0.87)

                vibrationDataUnFiltered = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)

                vibrationData = bandPassFilter(vibrationDataUnFiltered,highPass,lowPass,samplingFrequency)
                accTwfEnvelope = getEnvelope(vibrationData)

                accSptrmEnvelope, _ = getFFT(accTwfEnvelope, samplingFrequency)
                accSptrmEnvelope = [round(k, 4) for k in accSptrmEnvelope]
                finalData.update({axis: accSptrmEnvelope})
                finalData.update({"max": round(max(accSptrmEnvelope), 4)})

                x_axis_data = models.SpectrumChartDataMaster.objects.filter(composite=composite_id, timestamp=data.get('timestamp'))
                x_axis_data_serializer = serializers.SpectrumChartDataMasterSerializer(x_axis_data[0])
                x_axis_jsondata = json.loads(json.dumps(x_axis_data_serializer.data))
                finalData.update({"x_axis_spectrum_data":[float(i) for i in x_axis_jsondata['acceleration']]})
                return Response(finalData, status=status.HTTP_200_OK)
            except:
                return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)
        
# @api_view(['POST'])
# def AssetReportTrend(request):
#     if request.method == 'POST':
#         try:
#             data = JSONParser().parse(request)
#             if not data:
#                 return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

#             composite_key = data.get("composite_key")
#             singleDeviceData = {'_id':composite_key}

#             try:
#                 device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
#                 mount_id = "_"+str(device_mount_data.id)    # did for portable sensor as composite_id keeps on rotating
#                 # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
#             except:
#                 return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)

#             try:
#                 timestamp_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id).latest('timestamp')
#             except models.VelocityStatTimeMaster.DoesNotExist:
#                 return Response({'message':'Trend data not found'},status=status.HTTP_404_NOT_FOUND)
#             axis_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id,\
#                 timestamp__lte=timestamp_data.timestamp).order_by('-timestamp')
#             individualData = []
#             timestampList = []

#             if len(axis_data)>0:
#                 for singleaxis in reversed(axis_data):

#                     # need logic to convert datetime to country specific dynamically
#                     ist_date = singleaxis.timestamp
                    
#                     individualData.append({
#                         'timestamp':ist_date.timestamp(),\
#                         'axis': singleaxis.axis,\
#                         'data':{'rms':singleaxis.rms
#                         }
#                         })
#                     if ist_date.timestamp() not in timestampList:
#                         timestampList.append(ist_date.timestamp())
#                 finalRMSData = []
#                 for sintimestamp in timestampList:
#                     singleRMSData = {'timestamp':sintimestamp}
#                     for sinrms in individualData:
#                         if sintimestamp == sinrms['timestamp']:
#                             singleRMSData.update({sinrms['axis']:sinrms['data']})
#                     finalRMSData.append(singleRMSData)
#                 newFinalData = []
#                 for singlePoint in finalRMSData:
#                     if (singlePoint.keys() >= {'timestamp','Axial','Horizontal','Vertical'}):
#                         newFinalData.append(singlePoint)
#                     else:
#                         allKeysList = ['timestamp','Axial','Horizontal','Vertical']
#                         absentKeys = [k for k in allKeysList if k not in list(singlePoint.keys())]
#                         for i in absentKeys:
#                             singlePoint.update({i: {'rms': 'NA'}})
#                         newFinalData.append(singlePoint)

#                 singleDeviceData.update({'rms':newFinalData})
#                 return Response(singleDeviceData,status=status.HTTP_200_OK)

#             else:
#                 return Response({'message':'Trend Data not found'},status=status.HTTP_404_NOT_FOUND)

#         except:
#             return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


#     return True


@api_view(['POST'])
def AssetReportTrend(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

            composite_key = data.get("composite_key")
            singleDeviceData = {'_id':composite_key}
            fromDate = data.get("fromDate")
            toDate = data.get("toDate")
            function_filter = Q(**{'rms__lte': 45}) & Q(**{'rms__isnull': False})
            try:
                device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                # mount_id = "_"+str(device_mount_data.id)    # did for portable sensor as composite_id keeps on rotating
                mount_id = device_mount_data.id
                # sensor_orient_data = models.SensorOrientationMaster.objects.get(position=device_mount_data.mount_direction)
            except:
                return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)

            function = 'rms'
            axisList = ['Axial', 'Horizontal', 'Vertical']
            fields = [f"{function}_{axis}" for axis in axisList]
            function_filter = Q()
            for field in fields:
                function_filter &= Q(**{f"{field}__lte": 100}) & Q(**{f"{field}__isnull": False})

            axis_data_ids = models.VelocityStatTimeOptimized.objects.filter(
                Q(mount_id=mount_id) & 
                function_filter
            ).order_by('-timestamp').values_list('id', flat=True)[:150]
            axis_data = models.VelocityStatTimeOptimized.objects.filter(id__in=axis_data_ids).values_list(*fields).order_by("timestamp")
            if axis_data.exists():
                max_values = {"max": max(value[0] for value in axis_data)}
                selected_columns = ['timestamp'] + fields
                data = axis_data.values(*selected_columns)

                axis_data = []
                for row in data:
                    transformed_item = {
                        "timestamp": row['timestamp'].timestamp(),
                    }
                    for key, value in row.items():
                        if key.startswith(function+"_") and key != "rms_only":
                            axis_name = key.replace(function+"_", "")
                            transformed_item[axis_name] = {function: float(value)}
                    axis_data.append(transformed_item)
            else:
                return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
            
            newFinalData = []

            if len(axis_data)>0:
                for singlePoint in axis_data:
                    if (singlePoint.keys() >= {'timestamp','Axial','Horizontal','Vertical'}):
                        newFinalData.append(singlePoint)
                    else:
                        allKeysList = ['timestamp','Axial','Horizontal','Vertical']
                        absentKeys = [k for k in allKeysList if k not in list(singlePoint.keys())]
                        for i in absentKeys:
                            singlePoint.update({i: {'rms': 'NA'}})
                        newFinalData.append(singlePoint)

                singleDeviceData.update({'rms':newFinalData})
                return Response(singleDeviceData,status=status.HTTP_200_OK)

            else:
                return Response({'message':'Trend Data not found'},status=status.HTTP_404_NOT_FOUND)

        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


    return True


# class SaveRMSData(APIView):

#     def get(self, request):
#         df = JSONParser().parse(request)
#         return True
    
#     def post(self, request):

#         # pdb.set_trace()
#         df = JSONParser().parse(request)
#         if not df:
#                 return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
#         # print("dfffffffffffffffff", df)
#         macId = 'w_' + df.get("mac")
#         sensorType = "w"
#         timestamp = df.get("timestamp")
#         aRMSx = df.get("aRMSx")
#         aRMSy = df.get("aRMSy")
#         aRMSz = df.get("aRMSz")
#         vRMSx = df.get("vRMSx")
#         vRMSy = df.get("vRMSy")
#         vRMSz = df.get("vRMSz")
#         temperature = df.get("temperature")
#         tFlag = False
#         aFlag = False
#         vFlag = False


#         utc_dt = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.utc)
#         local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))

#         try:
#             # pdb.set_trace()

#             ########################## function is only for wired version to save edge RMS values ##########################
#             try:
#                 device_data = models.DeviceMountMaster.objects.get(mac_id=macId, is_linked=True)
#                 asset_id = device_data.asset_id
#                 composite_key = device_data.composite_id
#                 mount_id = device_data.id
#                 sensorOrientation = device_data.mount_direction
#                 sesnorOrientData = models.SensorPositionMaster.objects.get(sensor_type=sensorType)
#                 axisInfo = sesnorOrientData.orientation.get(sensorOrientation)
#             except models.DeviceMountMaster.DoesNotExist:
#                 print("unmapped sensor ", macId)
#                 return Response({'message':'Unable to fetech device. Contact admin...'},status=status.HTTP_404_NOT_FOUND)
            
#             dataAccelerationStatTimeMaster = [
#                 models.AccelerationStatTimeMaster(timestamp = local_dt, rms = aRMSx, axis = axisInfo.get("x"), composite = composite_key, asset_id = asset_id, rms_only = True),
#                 models.AccelerationStatTimeMaster(timestamp = local_dt, rms = aRMSy, axis = axisInfo.get("y"), composite = composite_key, asset_id = asset_id, rms_only = True),
#                 models.AccelerationStatTimeMaster(timestamp = local_dt, rms = aRMSz, axis = axisInfo.get("z"), composite = composite_key, asset_id = asset_id, rms_only = True)
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
#                     tFlag = True
#             except:
#                 print("temp data error")
            
#             try:
#                 accModel = models.AccelerationStatTimeMaster.objects.bulk_create(dataAccelerationStatTimeMaster)
#                 aFlag = True
#             except:
#                 print("acceleration data error")
            
#             try:
#                 velModel = models.VelocityStatTimeMaster.objects.bulk_create(dataVelocityStatTimeMaster)
#                 vFlag = True
#             except:
#                 print("velocity data error")
#             if tFlag and aFlag and vFlag:
#                 return Response({"message": "All data saved"}, status = status.HTTP_200_OK)
#             elif not tFlag:
#                 return Response({"message": "Something wrong with temperature data."}, status = status.HTTP_400_BAD_REQUEST)
#             elif not aFlag:
#                 return Response({"message": "Something wrong with acceleration data."}, status = status.HTTP_400_BAD_REQUEST)
#             elif not vFlag:
#                 return Response({"message": "Something wrong with velocity data."}, status = status.HTTP_400_BAD_REQUEST)
#             else:
#                 return Response({"message": "Something went wrong, kindly contact admin."}, status = status.HTTP_400_BAD_REQUEST)
#         except:
#             return Response({"message": "Something went wrong, kindly contact admin."}, status = status.HTTP_400_BAD_REQUEST)
            

class AutoThreshold(APIView):

    def get(self, request, *args, **kwargs):
        # pdb.set_trace()
        try:
            asset_id = kwargs.get("param1")
            assetFlagData = models.DynamicThresholdType.objects.filter(asset_id = asset_id)
            if len(assetFlagData) > 0:
                asstFlagSerializer = serializers.DynamicThresholdTypeSerializer(assetFlagData[0])
                return Response({"status": True, "data": asstFlagSerializer.data}, status=status.HTTP_200_OK)
            else:
                resData = {"asset_id": asset_id, "is_dynamic": False}
                return Response({"status": True, "data": resData}, status=status.HTTP_200_OK)

        except:
            return Response({"status": False, "message": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)       

    def post(self, request, *args, **kwargs):
        df = JSONParser().parse(request)
        if not df:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        asset_id = df.get("asset_id")
        flag = df.get("flag")
        try:
            try:
                existingAsset = models.DynamicThresholdType.objects.get(asset_id=asset_id)
                existingAsset.is_dynamic = flag
                existingAsset.save()
                return Response({"message": "Flag updated successfully."}, status = status.HTTP_200_OK)
            except:
                dataObject = {"asset_id": asset_id, "is_dynamic": flag}
                thresSerialize = serializers.DynamicThresholdTypeSerializer(data=dataObject)
                if thresSerialize.is_valid():
                    thresSerialize.save()
                    return Response({'message': "Flag updated successfully."}, status=status.HTTP_201_CREATED)
        except:
            return Response({"message": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)
        

@api_view(['POST'])
def get_auto_correlation(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin.'},\
                status=status.HTTP_404_NOT_FOUND)

        try:
            device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            mount_id = "_"+str(device_mount_data.id)
        except:
            return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
        
        try:
            singleDeviceData = {'_id':composite_key}
            # pdb.set_trace()
            if dataTimestamp:
                singleDeviceData.update({'timestamp':dataTimestamp})
                try:
                    try:
                        auto_corr_data = models.AutoCorrelationMaster.objects.\
                            filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=dataAxis)
                    except:
                        return Response({'message':'Auto-Correlation Data not found'},status=status.HTTP_404_NOT_FOUND)
                    auto_corr_data_serializer = serializers.AutoCorrelationMasterSerializer(auto_corr_data, many=True)
                    for singleData in auto_corr_data_serializer.data:
                        jsondata = json.loads(json.dumps(singleData))
                        singleDeviceData.update({dataAxis:[float(i) for i in jsondata['data']], 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})

                except:
                    return Response({'message':'Something went wrong...'},status=status.HTTP_404_NOT_FOUND)

        except:
            return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)


def getScale(amp_1, amp_2, amp_3, amp_4):

    level_1 = round((amp_1/amp_4), 2)
    level_2= round((amp_2/amp_4), 2)
    level_3 = round((amp_3/amp_4), 2)
    level_4 = round((amp_4/amp_4), 2)

    return level_1, level_2, level_3, level_4



# class GetAssetRmsTempKpi(APIView):


#     def post(self, request, *args, **kwargs):
#         df = JSONParser().parse(request)
#         if not df:
#             return Response({'message': "Json Data not found."}, status=status.HTTP_404_NOT_FOUND)
        
#         composite_key = df.get("composite")
#         axisList = ["Axial", "Horizontal", "Vertical", "temp"]
#         signalList = ['velocity', 'acceleration', 'temp']
#         result = {}

#         if composite_key == "no_endpoint":
#             return Response({"No data available"}, status=status.HTTP_200_OK)
#         else:
#             mount_id = "_" + str(composite_key.split("_")[-1])
#             try:
#                 # Pre-fetch all threshold values for the composite and signals
#                 threshold_values = models.ThresholdValues.objects.filter(
#                     composite__endswith=mount_id,
#                     signal_type__in=signalList,
#                     axis__in=axisList
#                 )

#                 threshold_dict = {
#                     (th.axis, th.signal_type): th for th in threshold_values
#                 }

#                 for signal in signalList:
#                     signal_obj = {}
#                     if signal == "velocity":
#                         sv = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, axis__in=axisList).order_by("-timestamp")[:10]
#                     elif signal == "acceleration":
#                         sv = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id, axis__in=axisList).order_by("-timestamp")[:10]
#                     elif signal == "temp":
#                         if composite_key == "ble_D5:73:29:01:CA:37_66f55613bcc52d144f4140d3_3658":
#                             composite_key = "ble_CD:B2:F8:13:19:59_66f55613bcc52d144f4140d3_3652"
#                             mount_id = 3652
#                             adjusted_temp = 12
#                         else:
#                             adjusted_temp = 0
#                         sv = models.TemperatureMaster.objects.filter(composite__endswith=mount_id).order_by("-timestamp")[:10]
#                     stat_values_dict = {single.axis: single for single in reversed(sv)}
#                     for single_axis in axisList:
#                         axisThresData = threshold_dict.get((single_axis, signal))
#                         if axisThresData:
#                             if signal in ['acceleration', 'velocity']:
#                                 amp_one = axisThresData.rms_amp_level_1
#                                 amp_two = axisThresData.rms_amp_level_2
#                                 amp_three = axisThresData.rms_amp_level_3
#                                 amp_four = round((amp_three + (amp_three - amp_two) / 2), 2)
#                                 try:
#                                     level_1, level_2, level_3, level_4 = getScale(amp_one, amp_two, amp_three, amp_four)
#                                 except:
#                                     level_1 = 0
#                                     level_2 = 0
#                                     level_3 = 0
#                                     level_4 = 0

#                                 if single_axis in ["Axial", "Horizontal", "Vertical"]:
#                                     single_axis_data = stat_values_dict.get(single_axis)

#                                 if single_axis_data:
#                                     signal_obj.update({
#                                         single_axis: {
#                                             'title': single_axis,
#                                             'value': single_axis_data.rms,
#                                             'max': amp_four,
#                                             'axisLine': [
#                                                 [level_1, '#51FC4C'],
#                                                 [level_2, '#F7FA4B'],
#                                                 [level_3, '#FA8349'],
#                                                 [level_4, '#ff0000']
#                                             ]
#                                         }
#                                     })

#                             if signal == 'temp':
#                                 amp_one = axisThresData.temp_amp_level_1
#                                 amp_two = axisThresData.temp_amp_level_2
#                                 amp_three = axisThresData.temp_amp_level_3
#                                 amp_four = round((amp_three + (amp_three - amp_two) / 2), 2)
#                                 try:
#                                     level_1, level_2, level_3, level_4 = getScale(amp_one, amp_two, amp_three, amp_four)
#                                 except:
#                                     level_1 = 0
#                                     level_2 = 0
#                                     level_3 = 0
#                                     level_4 = 0

#                                 if single_axis == "temp":
#                                     single_axis_data = stat_values_dict.get(single_axis)

#                                 if single_axis_data:
#                                     if single_axis_data.temp < level_1:
#                                         color = '#5151a9'
#                                         temp_status = 'Healthy'
#                                     elif level_1 <= single_axis_data.temp < level_2:
#                                         color = '#5151a9'
#                                         temp_status = 'Alert'
#                                     elif level_2 <= single_axis_data.temp < level_3:
#                                         color = '#5151a9'
#                                         temp_status = 'Danger'
#                                     elif level_3 <= single_axis_data.temp:
#                                         color = '#5151a9'
#                                         temp_status = 'Critical'

#                                     signal_obj.update({
#                                         single_axis: {
#                                             'title': 'Temperature',
#                                             'value': single_axis_data.temp + adjusted_temp,
#                                             'color': color,
#                                             'status': temp_status
#                                         }
#                                     })
#                         else:
#                             single_axis_data = stat_values_dict.get(single_axis)
#                             if single_axis_data:
#                                 if signal in ['acceleration', 'velocity'] and single_axis in ["Axial", "Horizontal", "Vertical"]:
#                                     signal_obj.update({
#                                         single_axis: {
#                                             'title': single_axis,
#                                             'value': single_axis_data.rms,
#                                             'max': 1,
#                                             'axisLine': [
#                                                 [1, '#5151a9']
#                                             ]
#                                         }
#                                     })
#                                 if signal == 'temp' and single_axis == 'temp':
#                                     signal_obj.update({
#                                         single_axis: {
#                                             'title': 'Temperature',
#                                             'value': single_axis_data.temp + adjusted_temp,
#                                             'color': '#5151a9'
#                                         }
#                                     })
#                             else:
#                                 if signal in ['acceleration', 'velocity'] and single_axis in ["Axial", "Horizontal", "Vertical"]:
#                                     signal_obj.update({
#                                         single_axis: {
#                                             'title': single_axis,
#                                             'value': 0,
#                                             'max': 1,
#                                             'axisLine': [
#                                                 [1, '#b5b5b5']
#                                             ]
#                                         }
#                                     })
#                                 elif signal == 'temp' and single_axis == 'temp':
#                                     signal_obj.update({
#                                         single_axis: {
#                                             'title': 'Temperature',
#                                             'value': '-',
#                                             'color': '#b5b5b5'
#                                         }
#                                     })
#                     result.update({signal: signal_obj})

#                 return Response(result, status=status.HTTP_200_OK)
#             except Exception as e:
#                 print("exception in GetAssetRmsTempKpi", e)
#                 return Response({"message": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


class GetAssetRmsTempKpi(APIView):


    def post(self, request, *args, **kwargs):
        df = JSONParser().parse(request)
        if not df:
            return Response({'message': "Json Data not found."}, status=status.HTTP_404_NOT_FOUND)
        # pdb.set_trace()
        composite_key = df.get("composite")
        axisList = ["Axial", "Horizontal", "Vertical", "temp"]
        signalList = ['velocity', 'acceleration', 'temp']
        result = {}

        if composite_key == "no_endpoint":
            return Response({"No data available"}, status=status.HTTP_200_OK)
        else:
            mount_id = "_" + str(composite_key.split("_")[-1])
            try:
                # Pre-fetch all threshold values for the composite and signals
                threshold_values = models.ThresholdValues.objects.filter(
                    composite__endswith=mount_id,
                    signal_type__in=signalList,
                    axis__in=axisList
                )

                threshold_dict = {
                    (th.axis, th.signal_type): th for th in threshold_values
                }

                newMount = composite_key.split("_")[-1]
                deviceObject = models.DeviceMountMaster.objects.get(id=newMount)
                timezone = deviceObject.timezone
                for signal in signalList:
                    signal_obj = {}
                    if signal == "velocity":
                        single_axis_data = models.VelocityStatTimeOptimized.objects.filter(mount_id=newMount).latest('timestamp')
                            
                    elif signal == "acceleration":
                        single_axis_data = models.AccelerationStatTimeOptimized.objects.filter(mount_id=newMount).latest('timestamp')

                    elif signal == "temp":
                        if composite_key == "ble_D5:73:29:01:CA:37_66f55613bcc52d144f4140d3_3658":
                            composite_key = "ble_CD:B2:F8:13:19:59_66f55613bcc52d144f4140d3_3652"
                            mount_id = 3652
                            adjusted_temp = 12
                        else:
                            adjusted_temp = 0
                        single_axis_data = models.TemperatureMaster.objects.filter(mount_id=newMount).latest('timestamp')

                    for single_axis in axisList:
                        axisThresData = threshold_dict.get((single_axis, signal))
                        if axisThresData:
                            if signal in ['acceleration', 'velocity']:
                                amp_one = axisThresData.rms_amp_level_1
                                amp_two = axisThresData.rms_amp_level_2
                                amp_three = axisThresData.rms_amp_level_3
                                amp_four = round((amp_three + (amp_three - amp_two) / 2), 2)
                                try:
                                    level_1, level_2, level_3, level_4 = getScale(amp_one, amp_two, amp_three, amp_four)
                                except:
                                    level_1 = 0
                                    level_2 = 0
                                    level_3 = 0
                                    level_4 = 0

                                # if single_axis in ["Axial", "Horizontal", "Vertical"]:
                                #     single_axis_data = stat_values_dict.get(single_axis)

                                if single_axis_data:
                                    signal_obj.update({
                                        single_axis: {
                                            'title': single_axis,
                                            # 'value': single_axis_data.rms,
                                            'value': getattr(single_axis_data, f'rms_{single_axis}'),
                                            'max': amp_four,
                                            'axisLine': [
                                                [level_1, '#51FC4C'],
                                                [level_2, '#F7FA4B'],
                                                [level_3, '#FA8349'],
                                                [level_4, '#ff0000']
                                            ]
                                        }
                                    })

                            if signal == 'temp':
                                amp_one = axisThresData.temp_amp_level_1
                                amp_two = axisThresData.temp_amp_level_2
                                amp_three = axisThresData.temp_amp_level_3
                                amp_four = round((amp_three + (amp_three - amp_two) / 2), 2)
                                try:
                                    level_1, level_2, level_3, level_4 = getScale(amp_one, amp_two, amp_three, amp_four)
                                except:
                                    level_1 = 0
                                    level_2 = 0
                                    level_3 = 0
                                    level_4 = 0

                                # if single_axis == "temp":
                                #     single_axis_data = stat_values_dict.get(single_axis)

                                if single_axis_data:
                                    if single_axis_data.temp < level_1:
                                        color = '#5151a9'
                                        temp_status = 'Healthy'
                                    elif level_1 <= single_axis_data.temp < level_2:
                                        color = '#5151a9'
                                        temp_status = 'Alert'
                                    elif level_2 <= single_axis_data.temp < level_3:
                                        color = '#5151a9'
                                        temp_status = 'Danger'
                                    elif level_3 <= single_axis_data.temp:
                                        color = '#5151a9'
                                        temp_status = 'Critical'

                                    signal_obj.update({
                                        single_axis: {
                                            'title': 'Temperature',
                                            'value': single_axis_data.temp + adjusted_temp,
                                            'color': color,
                                            'status': temp_status
                                        }
                                    })
                        else:
                            # single_axis_data = stat_values_dict.get(single_axis)
                            if single_axis_data:
                                if signal in ['acceleration', 'velocity'] and single_axis in ["Axial", "Horizontal", "Vertical"]:
                                    signal_obj.update({
                                        single_axis: {
                                            'title': single_axis,
                                            'value': getattr(single_axis_data, f'rms_{single_axis}'),
                                            'max': 1,
                                            'axisLine': [
                                                [1, '#5151a9']
                                            ]
                                        }
                                    })
                                if signal == 'temp' and single_axis == 'temp':
                                    signal_obj.update({
                                        single_axis: {
                                            'title': 'Temperature',
                                            'value': single_axis_data.temp + adjusted_temp,
                                            'color': '#5151a9'
                                        }
                                    })
                            else:
                                if signal in ['acceleration', 'velocity'] and single_axis in ["Axial", "Horizontal", "Vertical"]:
                                    signal_obj.update({
                                        single_axis: {
                                            'title': single_axis,
                                            'value': 0,
                                            'max': 1,
                                            'axisLine': [
                                                [1, '#b5b5b5']
                                            ]
                                        }
                                    })
                                elif signal == 'temp' and single_axis == 'temp':
                                    signal_obj.update({
                                        single_axis: {
                                            'title': 'Temperature',
                                            'value': '-',
                                            'color': '#b5b5b5'
                                        }
                                    })
                    result.update({signal: signal_obj})

                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                print("exception in GetAssetRmsTempKpi", e)
                return Response({"message": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)
            
            
@api_view(['POST'])
def getGatewayDeviceList(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        org_id = data.get("account_id")
        gateway_mac_id = data.get("gateway_mac_id")
        try:
            try:
                existingGateData = models.GatewayMountMaster.objects.get(gateway_mac_id=gateway_mac_id, org_id=org_id)
            except:
                return Response({'message':'Provided gateway mac id not found, kindly check.'},status=status.HTTP_404_NOT_FOUND)
            mappedSensors = existingGateData.device_list
            finalData = {}
            try:
                mappedSensorData = models.DeviceMountMaster.objects.filter(mac_id__in=mappedSensors, org_id=org_id, is_linked=True)
                mappedSensorDataSerializer = serializers.DeviceMountMasterSerializer(mappedSensorData,  many=True)
                foundSensors = json.loads(json.dumps(mappedSensorDataSerializer.data))
                # print("mappedSensorDatamappedSensorDatamappedSensorData", mappedSensorData)
                # if len(mappedSensorData) > 0:
                #     for singledevice in mappedSensorData:
                #         deviceSerializer = serializers.DeviceMountMasterSerializer(singledevice)
                #         deviceSerializerData = json.loads(json.dumps(deviceSerializer.data))
                #         sensorList.append(deviceSerializerData)
                #     print("sensorListsensorList", sensorList)
                # finalData.update({"gateway_id":gateway_mac_id, "sensor_list": sensorList})
                foundSensorsDict = {item['mac_id']: item for item in foundSensors}
                result = [foundSensorsDict.get(mac_id, 
                                               {"is_linked": False,
                                                "composite_id":  "-",
                                                "message":  "Sensor not mapped to asset",
                                                "point_name":  "-",
                                                "mount_location":  "-",
                                                "mount_type": "-",
                                                "mount_material": "-",
                                                "mount_direction":  "-",
                                                "asset_id":  "-",
                                                "org_id":  "-",
                                                "mac_id": mac_id,
                                                "image": "-"}
                                               ) for mac_id in mappedSensors]
                finalData.update({"gateway_id":gateway_mac_id, "sensor_list": result})
                return Response({'data': finalData}, status=status.HTTP_200_OK)
            except:
                return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def getGatewayList(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        org_id = data.get("account_id")
        locations = data.get("location_list")
        if locations:
            location_list = [i.get("location_id") for i in locations]
        finalLocationData = {'org_id': org_id}
        # ***************************** Get list of unique mac_id when only company_code is available *****************************
        # pdb.set_trace()
        try:
            allGateWayData = models.GatewayMountMaster.objects.filter(location_id__in=location_list, org_id=org_id)
            allGateWayDataSerializer = serializers.GatewayMountMasterSerializer(allGateWayData,  many=True)
            if len(allGateWayData) > 0:
                # gatewayList = [i.gateway_mac_id for i in allGateWayData]
                # for loc in locations:
                location_details_map = {loc["location_id"]: loc for loc in locations}

                for item in list(allGateWayDataSerializer.data):
                    location_id = item["location_id"]
                    if location_id in location_details_map:
                        location_details = location_details_map[location_id]
                        item.update(location_details)

                finalLocationData.update({'mac_id_list':allGateWayDataSerializer.data})

                return Response({'data': finalLocationData}, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No gateway data found.'})
        except:
            return Response({'message': "Something went wrong, kindly try after sometime."}, status=status.HTTP_400_BAD_REQUEST)



# @api_view(['POST'])
# def getAcousticSpectrum(request):
#     if request.method == 'POST':
#         data = JSONParser().parse(request)
#         if not data:
#             return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
#         composite = data.get("composite_key")
#         mount_id = composite.split("_")[-1]
#         dataTimestamp = data.get("timestamp")

#         if dataTimestamp:
#                 try:
#                     utc_dt = datetime.utcfromtimestamp(dataTimestamp).replace(tzinfo=pytz.utc)
#                     local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
#                 except:
#                     return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
#                 data.update({'timestamp':local_dt})

#         acoustic_data = models.AcousticsSpectrumMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'))
#         acoustic_data_serializer = serializers.AcousticsSpectrumMasterSerializer(acoustic_data[0])
#         final_data = acoustic_data_serializer.data
#         if composite in ['ble_FD:A4:C8:32:9C:EB_67178104a58fd75e0c74a440_3723', 'ble_FF:4B:4F:9C:E4:34_67178104a58fd75e0c74a440_3724','ble_D9:72:23:F0:78:C2_67178104a58fd75e0c74a440_3725','ble_FE:90:0C:2E:BC:C9_67178104a58fd75e0c74a440_3726']:
#             final_data['frequency_data_10k'] = []
#             final_data['spectrum_data_10k'] = []
#         return Response({"data": final_data}, status=status.HTTP_200_OK)


@api_view(['POST'])
def FloorMapHealthKpi(request):
    if request.method == 'POST':
        try:

            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            payload = data.get("data")
            allAssets = []
            finalData = []
            for i in payload:
                asset_list = [j.get("id") for j in i.get("assetList") if len(i.get("assetList"))>0]
                allAssets += asset_list
            
            if len(allAssets) > 0:
                try:
                    assetHealth = models.AssetHealthMaster.objects.filter(asset_id__in=allAssets)
                    assetHealthList = list(assetHealth.values('status', 'asset_id'))


                    # Subquery to get the latest timestamp for each composite
                    latest_timestamp_subquery = models.TemperatureMaster.objects.filter(
                        composite=OuterRef('composite')
                    ).order_by('-timestamp').values('timestamp')[:1]
                    # print("------------------------", latest_timestamp_subquery)

                    # Main queryset to get the latest temperature for each composite
                    assetTemp = models.TemperatureMaster.objects.filter(
                        timestamp=Subquery(latest_timestamp_subquery),
                        asset_id__in=allAssets
                    ).values('asset_id', 'composite', 'temp', 'timestamp')



                    # temp data query
                    # assetTemp = models.TemperatureMaster.objects.filter(asset_id__in=allAssets).values('asset_id').annotate(latest_timestamp=Max('timestamp'),highest_temp=Max('temp'))
                    assetTempList = list(assetTemp)
                    for i in payload:
                        graphData = {
                                "tooltip": {
                                    "trigger": 'item'
                                },
                                "legend": {
                                    "show": False
                                },
                                "color": ["#FB565A", "#FA8349", "#F7FA4B", "#51FC4C", "#b0b0b0"],
                                "series": [
                                    {
                                    "name": 'Access From',
                                    "type": 'pie',
                                    "radius": ['50%', '85%'],
                                    "avoidLabelOverlap": False,
                                    "label": {
                                        "show": False,
                                        "position": 'center'
                                    },
                                    "emphasis": {
                                        "label": {
                                        "show": False,
                                        "fontSize": 40,
                                        "fontWeight": 'bold'
                                        }
                                    },
                                    "labelLine": {
                                        "show": False
                                    },
                                    "data": []
                                    }
                                ],
                                "graphic": [
                                    {
                                    "type": 'circle',
                                    "left": 'center',
                                    "top": 'center',
                                    "z": 100,
                                    "shape": {
                                        "r": 15
                                    },
                                    "style": {
                                        "fill": '#fff'
                                    },
                                    },
                                    {
                                    "type": 'text',
                                    "left": 'center',
                                    "top": 'center',
                                    "z": 101,
                                    "style": {
                                        "text": 0,
                                        "fill": '#000',
                                        "fontSize": 20,
                                        "fontWeight": 'bold'
                                    }
                                    }
                                ]
                            }
                        asset_health_data = [
                            {"value": 0, "name":"Critical"},
                            {"value": 0, "name": "Danger"},
                            {"value": 0, "name": "Alert"},
                            {"value": 0, "name": "Healthy"},
                            {"value": 0, "name": "Not Defined"}
                            ]
                        totalAssets = len(i.get("assetList"))
                        singleLocationAssetList = [j.get("id") for j in i.get("assetList") if len(i.get("assetList"))>0]
                        graphData['graphic'][1]['style']['text'] = totalAssets

                        """finding and updating each asset health status"""
                        # singleLocationAssetListHealth1 = assetHealth.filter(asset_id__in=singleLocationAssetList).values('status', 'asset_id')
                        status_map = {item['asset_id']: item['status'] for item in assetHealthList}
                        for item in i.get("assetList"):
                            item['status'] = status_map.get(item['id'], 'Not Defined')

                        # Sorting order for statuses
                        status_order = ["Critical", "Danger", "Alert", "Healthy", "Not Defined"]

                        # Sort assets based on status order
                        sorted_assets = sorted(i.get("assetList"), key=lambda x: status_order.index(x['status']))
                        i["assetList"] = sorted_assets

                        
                        """finding and updating each asset health status"""
                        temp_map = {item['asset_id']: float(item['temp']) for item in assetTempList}
                        date_map = {item['asset_id']: item['timestamp'].timestamp() for item in assetTempList}
                        for item in i.get("assetList"):
                            item['temp'] = temp_map.get(item['id'], '-')
                            item['lastCollected'] = date_map.get(item['id'], '-')

                        # singleLocationAssetListHealth = assetHealth.filter(asset_id__in=singleLocationAssetList).values('status').annotate(count=Count("asset_id"))4
                        statusCounter = Counter(item['status'] for item in assetHealthList if item['asset_id'] in singleLocationAssetList)
                        singleLocationAssetListHealth = [{'status': status, 'count': count} for status, count in statusCounter.items()]
                        if len(singleLocationAssetListHealth) > 0:
                            for health in singleLocationAssetListHealth:
                                if health.get("status") == "Critical":
                                    asset_health_data[0]["value"] = health.get("count")
                                elif health.get("status") == "Danger":
                                    asset_health_data[1]["value"] = health.get("count")
                                elif health.get("status") == "Alert":
                                    asset_health_data[2]["value"] = health.get("count")
                                elif health.get("status") == "Healthy":
                                    asset_health_data[3]["value"] = health.get("count")
                                elif health.get("status") == "Not Defined":
                                    asset_health_data[4]["value"] = health.get("count")
                                else:
                                    pass
                            graphData['series'][0]['data'] = asset_health_data
                            i.update({"graph_data": graphData})
                            finalData.append(i)
                        else:
                            graphData['series'][0]['data'] = asset_health_data  
                            i.update({"graph_data": graphData})
                            finalData.append(i)
                        
                    return Response({"data": finalData}, status=status.HTTP_200_OK)
                except Exception as e:
                    print("Exception in asset health model query", e)
            else:
                return Response({'message': 'No asset found under selected locations.'}, status=status.HTTP_404_NOT_FOUND)

            # for i in payload:
            #     print("-----------", i)
            #     print("*************************************************")
            return Response({'message': 'No asset found under selected locations.'}, status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message': 'Something went wrong, kindly contact admin.'}, status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
def GetMagnetisRMSData(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

        composite_key = data.get("mac_id")
        asset_id = data.get("assetId")
        axisList = data.get("axis", None)
        fromDate = data.get("fromDate")
        toDate = data.get("toDate")
        final_data = {"mac_id": data.get("mac_id") }
        # composite_key = mac_id + '_' + asset_id
        # pdb.set_trace()
        try:
            try:
                singleDeviceData = {'_id':composite_key}
                device_mount_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                mount_id = "_"+str(device_mount_data.id)
            except:
                return Response({'message':"Sensor Mount Configurations not correct."},status=status.HTTP_404_NOT_FOUND)
            if (fromDate and toDate):
                # newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                # newIncreasedDate = newToDate + timedelta(days=1)
                # acousticData = models.MagneticFluxStatMaster.objects.filter(composite__endswith=mount_id, \
                #     timestamp__range=[fromDate.split("T")[0],newIncreasedDate]).order_by('-timestamp')
                #     # timestamp__range=[fromDate.split("T")[0],toDate.split("T")[0]]).order_by('-timestamp')

                
                newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')
                newIncreasedDate = newToDate + timedelta(days=1)
                try:
                    axis_data_ids = models.MagneticFluxStatMaster.objects.filter(
                        Q(composite__endswith=mount_id)&
                        Q(axis__in=axisList)&
                        Q(timestamp__range=[fromDate.split("T")[0],newIncreasedDate])
                    ).values_list('id', flat=True)
                    # Filter the queryset by these IDs
                    axis_data = models.MagneticFluxStatMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")

                    if axis_data.exists():
                        max_values = axis_data.aggregate(max=Max('rms'))
                        # Fetch required fields in a single query
                        data = axis_data.values('timestamp', 'rms', 'axis')
                        
                        function_values = [{entry['axis']: {'rms': entry['rms']}, "timestamp": entry['timestamp'].timestamp()} for entry in data]

                    else:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                except models.MagneticFluxStatMaster.DoesNotExist:
                    return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                

            else:
                try:
                    timestamp_data = models.MagneticFluxStatMaster.objects.filter(composite__endswith=mount_id).latest('timestamp')
                except models.MagneticFluxStatMaster.DoesNotExist:
                    return Response({'message':'Magnetic trend data not found'},status=status.HTTP_404_NOT_FOUND)
                # pdb.set_trace()
                acousticData = models.MagneticFluxStatMaster.objects.filter(composite__endswith=mount_id,\
                            timestamp__lte=timestamp_data.timestamp).order_by('-timestamp')[:150]
                

                try:
                    axis_data_ids = models.MagneticFluxStatMaster.objects.filter(
                        Q(composite__endswith=mount_id) & 
                        Q(axis__in=axisList)
                    ).order_by('-timestamp').values_list('id', flat=True)[:150]
                    # Filter the queryset by these IDs
                    axis_data = models.MagneticFluxStatMaster.objects.filter(id__in=axis_data_ids).order_by("timestamp")

                    if axis_data.exists():
                        max_values = axis_data.aggregate(max=Max('rms'))
                        # Fetch required fields in a single query
                        data = axis_data.values('timestamp', 'rms', 'axis')
                        
                        function_values = [{entry['axis']: {'rms': entry['rms']}, "timestamp": entry['timestamp'].timestamp()} for entry in data]


                    else:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)
                except models.MagneticFluxStatMaster.DoesNotExist:
                        return Response({'message': 'Trend data not found'}, status=status.HTTP_404_NOT_FOUND)

            # pdb.set_trace()

            if len(axisList) > 1:
                # Create a dictionary to store merged data
                merged_data = defaultdict(dict)

                # Merge elements based on timestamp
                for item in function_values:
                    timestamp = item["timestamp"]
                    for key, value in item.items():
                        if key != "timestamp":
                            merged_data[timestamp][key] = value

                for ts, data in merged_data.items():
                    for key in ["Axial", "Vertical", "Horizontal"]:
                        if key not in data:
                            data[key] = {function: 'NA'}
                filtered_data = merged_data

                # Convert filtered data back to a list
                merged_list = [{"timestamp": ts, **data} for ts, data in filtered_data.items()]
                
            else:
                merged_list = function_values

            
            if len(axisList) == 1:
                """Function threshold values"""
                # try:
                #     thresholdData = models.ThresholdValues.objects.get(composite__endswith=mount_id, signal_type=signal_type, axis=axisList[0], domain='time')
                #     amp_one = getattr(thresholdData, function+"_amp_level_1")
                #     amp_two = getattr(thresholdData, function+"_amp_level_2")
                #     amp_three = getattr(thresholdData, function+"_amp_level_3")
                #     maxForGraph = max(max_values['max'], amp_one, amp_two, amp_three)
                #     singleDeviceData.update({"thres": {function+"_amp_level_1": amp_one, function+"_amp_level_2": amp_two, function+"_amp_level_3": amp_three}})
                # except Exception as e:
                #     print("exception in get_function_trend_data", e)
                #     maxForGraph = max_values['max']
                #     singleDeviceData.update({"thres": None})

                """Moving average trend line"""
                window_size = 5
                start = int(window_size/2)
                stop = window_size-start
                moving_avg_rms = []
                for i in range(0, len(function_values)):

                    if i < window_size - 1:
                        moving_avg_rms.append(round(float(np.mean([ i.get(axisList[0]).get('rms') for i in function_values[0:i+1]])), 3))
                    else:
                        moving_avg_rms.append(round(float(np.mean([ i.get(axisList[0]).get('rms') for i in function_values[i-window_size+1:i+1]])), 3))

                singleDeviceData.update({
                    "trendData": function_values,
                    "max": {"rms": max_values['max']},
                    'moving_average': {"rms": moving_avg_rms}
                    })
            else:
                singleDeviceData.update({
                    "trendData": merged_list,
                    "max": {'rms': max_values['max']},
                    })
            return Response(singleDeviceData, status=status.HTTP_200_OK)





            # acousticData_serializer = serializers.MagneticFluxStatMasterSerializer(acousticData, many=True)
            # acousticList = []
            # timestampList = []
            # if acousticData_serializer:
            #     for row in reversed(acousticData_serializer.data):
            #         jsondata = json.loads(json.dumps(row))
            #         timestampList.append(int(parser.isoparse(jsondata.get("timestamp")).timestamp()))
            #         # acousticList.append(float(jsondata.get("acoustic_rms")))
            #         acousticList.append(float(jsondata.get("rms")))
            # final_data.update({"timestamp":timestampList, "rms": acousticList})
            # return Response({'data':final_data, 'status_code': 200}, status=status.HTTP_200_OK) 
        


        except:
            return Response({'data':[], 'status_code': 400}, status=status.HTTP_200_OK) 
    except:
        return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)
    


@api_view(['POST'])
def getMagneticSpectrum(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        composite = data.get("composite_key")
        mount_id = composite.split("_")[-1]
        dataTimestamp = data.get("timestamp")
        axis = data.get("axis")

        if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(dataTimestamp).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp':local_dt})
        # pdb.set_trace()
        magnetic_data = models.MagneticFluxSpectrumMaster.objects.filter(composite__endswith=mount_id,timestamp=data.get('timestamp'), axis=axis)
        magnetic_data_serializer = serializers.MagneticFluxSpectrumMasterSerializer(magnetic_data[0])
        return Response({"data": magnetic_data_serializer.data}, status=status.HTTP_200_OK)
    



@api_view(['POST'])
def getEndpointKPIS(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        payload = data.get("data")
        try:
            compositeList = [i.get("end_point").get("id") for i in payload if i.get("end_point").get("id") is not None]
            queries = [models.VelocityStatTimeMaster.objects.filter(
                composite__endswith=f'_{id}'
            ).order_by('-timestamp').first() for id in compositeList]

            # Remove None results and combine them into a list
            latest_velocity = [q for q in queries if q is not None]
        except Exception as e:
            print("------------Exception--------------", e)
        return Response({"data": "All okay"}, status=status.HTTP_200_OK)



@api_view(['POST'])
def getAssetUtility(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        asset_id = data.get("asset_id")
        name_mapping = {
            'stop_condition': 'Stop Condition',
            'running_condition': 'Cutting Time',
            'ideal_condition': 'Normal Running',
            'power_down': 'Disconnected'
            }
        try:
            assetUtility = models.AssetUtilityMaster.objects.filter(asset_id=asset_id).latest('creation_date')
            assetUtilitySerializer = serializers.AssetUtilityMasterSerializer(assetUtility)
            final_data = assetUtilitySerializer.data

            # Initial data
            # abc = {'uptime': '6:30', 'downtime': '7:30', 'power_down': '10:00'}
            final_data['data'].pop('total_data_collected', None)

            # Convert each time to hours with minutes as decimals
            time_in_hours = {
                k: int(v.split(":")[0]) + int(v.split(":")[1]) / 60 for k, v in final_data.get('data').items()
            }

            # Total hours (which should be 24)
            total_hours = sum(time_in_hours.values())
            data_array = []
            # Update the dictionary with the new format
            for k, time_str in final_data.get("data").items():
                hours = time_in_hours[k]
                percentage = (hours / total_hours) * 100
                data_array.append({'name': name_mapping.get(k), 'hours': time_str, 'value': round(percentage, 2)})

            final_data['data'] = data_array

            return Response({'data': final_data}, status=status.HTTP_200_OK)
        except Exception as e:
            print("some exception", e)
            return Response({"message": "Something went wrong, kindly try after sometime"}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({"message": "Request type not allowed"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)




@api_view(['POST'])
def getAccelerationData(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            sensor_type, mac, asset_id, mount_id = composite_key.split("_")
            domain = data.get("domain")
            trendFunc = data.get("trendFunc", None)

            try:
                utc_dt = datetime.utcfromtimestamp(dataTimestamp).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                # return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                return {"status": "error", "message": "Unable to convert timestamp."}

            result = getRawDataFn(composite_key, dataTimestamp, local_dt, dataAxis, sensor_type)

            if result.get("status") == "error":
                return Response({'message': result.get("message")}, status=status.HTTP_404_NOT_FOUND)
            
            singleDeviceData = result.get("data")
            rData = singleDeviceData.get(dataAxis)
            fs = singleDeviceData.get('fs')
            
            accelerationTWF, accelerationSptrm, f_acc, twf_acc = omegaArithmeticNew(rData, 'acceleration', fs)

            if domain == "time":
                return Response(singleDeviceData,status=status.HTTP_200_OK)
            
            if domain == "frequency":
                if trendFunc == 'rms':
                    singleDeviceData.update({dataAxis: np.round(accelerationSptrm*0.707, 4)})
                else:
                    singleDeviceData.update({dataAxis:np.round(accelerationSptrm, 4)})

                singleDeviceData.update({"max": max(singleDeviceData[dataAxis])})
                singleDeviceData.update({
                            "signal_processing_details":{
                                            "sampling_frequency": singleDeviceData.get("fs"), "no_of_samples": singleDeviceData.get('no_of_samples'), \
                                                "high_pass": singleDeviceData.get('high_pass'), "low_pass": singleDeviceData.get('low_pass'), "rpm": singleDeviceData.get('rpm')
                                                }
                                            })
                singleDeviceData.update({"x_axis_spectrum_data":f_acc})
                try:
                    accStatData = models.AccelerationStatTimeOptimized.objects.filter(mount_id=mount_id, timestamp=local_dt).first()
                    singleDeviceData.update({
                        "stat_values": {
                            "rms": getattr(accStatData, 'rms_'+ dataAxis),
                            "axis": dataAxis, 
                            "peak": getattr(accStatData, 'peak_'+ dataAxis),
                            "peak_to_peak": getattr(accStatData, 'peak_to_peak_'+ dataAxis),
                        }
                    })
                except:
                    singleDeviceData.update({
                        "stat_values": {
                            "rms": "Na", "axis": "Na", "peak": "Na", "peak_to_peak": "Na"
                        }
                    })
                return Response(singleDeviceData,status=status.HTTP_200_OK)
        except:
            return Response({'message':'Something is wrong with the data. Please contact admin.'}, status=status.HTTP_404_NOT_FOUND)
    
@api_view(['POST'])
def getVelocityData(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            sensor_type, mac, asset_id, mount_id = composite_key.split("_")
            domain = data.get("domain")
            trendFunc = data.get("trendFunc", None)

            try:
                utc_dt = datetime.utcfromtimestamp(dataTimestamp).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                # return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                return {"status": "error", "message": "Unable to convert timestamp."}

            result = getRawDataFn(composite_key, dataTimestamp, local_dt, dataAxis, sensor_type)

            if result.get("status") == "error":
                return Response({'message': result.get("message")}, status=status.HTTP_404_NOT_FOUND)
            
            singleDeviceData = result.get("data")
            rData = singleDeviceData.get(dataAxis)
            fs = singleDeviceData.get('fs')

            velocityTWF, velocitySptrm, f_vel, twf_vel = omegaArithmeticNew(rData, 'velocity', fs)

            if domain == "time":
                singleDeviceData.update({dataAxis: np.round(velocityTWF, 4)})
                return Response(singleDeviceData,status=status.HTTP_200_OK)
            
            if domain == "frequency":
                if trendFunc == 'rms':
                    singleDeviceData.update({dataAxis: np.round(velocitySptrm*0.707, 4)})
                else:
                    singleDeviceData.update({dataAxis:np.round(velocitySptrm, 4)})

                singleDeviceData.update({"max": max(singleDeviceData[dataAxis])})
                singleDeviceData.update({
                            "signal_processing_details":{
                                            "sampling_frequency": singleDeviceData.get("fs"), "no_of_samples": singleDeviceData.get('no_of_samples'), \
                                                "high_pass": singleDeviceData.get('high_pass'), "low_pass": singleDeviceData.get('low_pass'), "rpm": singleDeviceData.get('rpm')
                                                }
                                            })
                singleDeviceData.update({"x_axis_spectrum_data":f_vel})

                try:
                    accStatData = models.VelocityStatTimeOptimized.objects.filter(mount_id=mount_id, timestamp=local_dt).first()
                    singleDeviceData.update({
                        "stat_values": {
                            "rms": getattr(accStatData, 'rms_'+ dataAxis),
                            "axis": dataAxis, 
                            "peak": getattr(accStatData, 'peak_'+ dataAxis),
                            "peak_to_peak": getattr(accStatData, 'peak_to_peak_'+ dataAxis),
                        }
                    })
                except:
                    singleDeviceData.update({
                        "stat_values": {
                            "rms": "Na", "axis": "Na", "peak": "Na", "peak_to_peak": "Na"
                        }
                    })

                return Response(singleDeviceData,status=status.HTTP_200_OK)

        except:
            return Response({'message':'Something is wrong with the data. Please contact admin.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)


@api_view(['POST'])
def getDisplacementData(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            sensor_type, mac, asset_id, mount_id = composite_key.split("_")
            domain = data.get("domain")
            trendFunc = data.get("trendFunc", None)

            try:
                utc_dt = datetime.utcfromtimestamp(dataTimestamp).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                # return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                return {"status": "error", "message": "Unable to convert timestamp."}

            result = getRawDataFn(composite_key, dataTimestamp, local_dt, dataAxis, sensor_type)

            if result.get("status") == "error":
                return Response({'message': result.get("message")}, status=status.HTTP_404_NOT_FOUND)
            
            singleDeviceData = result.get("data")
            rData = singleDeviceData.get(dataAxis)
            fs = singleDeviceData.get('fs')

            displacementTWF, displacementSptrm, f_dis, twf_dis = omegaArithmeticNew(rData, 'displacement', fs)

            if domain == "time":
                singleDeviceData.update({dataAxis: np.round(displacementTWF, 4)})
                return Response(singleDeviceData,status=status.HTTP_200_OK)
            
            if domain == "frequency":
                if trendFunc == 'rms':
                    singleDeviceData.update({dataAxis: np.round(displacementSptrm*0.707, 4)})
                else:
                    singleDeviceData.update({dataAxis:np.round(displacementSptrm, 4)})

                singleDeviceData.update({"max": max(singleDeviceData[dataAxis])})
                singleDeviceData.update({
                            "signal_processing_details":{
                                            "sampling_frequency": singleDeviceData.get("fs"), "no_of_samples": singleDeviceData.get('no_of_samples'), \
                                                "high_pass": singleDeviceData.get('high_pass'), "low_pass": singleDeviceData.get('low_pass'), "rpm": singleDeviceData.get('rpm')
                                                }
                                            })
                singleDeviceData.update({"x_axis_spectrum_data":f_dis})
                try:
                    accStatData = models.DisplacementStatTimeOptimized.objects.filter(mount_id=mount_id, timestamp=local_dt).first()
                    singleDeviceData.update({
                        "stat_values": {
                            "rms": getattr(accStatData, 'rms_'+ dataAxis),
                            "axis": dataAxis, 
                            "peak": getattr(accStatData, 'peak_'+ dataAxis),
                            "peak_to_peak": getattr(accStatData, 'peak_to_peak_'+ dataAxis),
                        }
                    })
                except:
                    singleDeviceData.update({
                        "stat_values": {
                            "rms": "Na", "axis": "Na", "peak": "Na", "peak_to_peak": "Na"
                        }
                    })
                return Response(singleDeviceData,status=status.HTTP_200_OK)

        except:
            return Response({'message':'Something is wrong with the data. Please contact admin.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)



@api_view(['POST'])
def getEnvelopeData(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            asset_id = data.get('assetId')
            dataAxis = data.get("axis")
            sensor_type, mac, asset_id, mount_id = composite_key.split("_")
            domain = data.get("domain")
            trendFunc = data.get("trendFunc", None)

            try:
                utc_dt = datetime.utcfromtimestamp(dataTimestamp).replace(tzinfo=pytz.utc)
                local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
            except:
                # return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
                return {"status": "error", "message": "Unable to convert timestamp."}

            result = getRawDataFn(composite_key, dataTimestamp, local_dt, dataAxis, sensor_type)

            if result.get("status") == "error":
                return Response({'message': result.get("message")}, status=status.HTTP_404_NOT_FOUND)
            
            singleDeviceData = result.get("data")
            rData = singleDeviceData.get(dataAxis)
            fs = singleDeviceData.get('fs')
            raw_axis = singleDeviceData.get('raw_axis')

            try:
                try:
                    high_pass_value, low_pass_value = getFilterValues(int(fs), raw_axis)
                except:
                    high_pass_value = 500
                    low_pass_value = 6000
                envRawData = rData - np.mean(rData)
                filteredEnvRawData = bandPassFilter(envRawData,high_pass_value, low_pass_value, int(fs))
                
            except:
                accTwfEnvelope = []
                accSptrmEnvelope = []

            if domain == "time":
                accTwfEnvelope = getEnvelope(filteredEnvRawData)
                singleDeviceData.update({dataAxis: np.round(accTwfEnvelope, 4)})
                return Response(singleDeviceData,status=status.HTTP_200_OK)
            # pdb.set_trace()
            if domain == "frequency":
                accTwfEnvelope = getEnvelope(filteredEnvRawData)
                accSptrmEnvelope, f_env = getFFT(accTwfEnvelope, fs)
                if trendFunc == 'rms':
                    singleDeviceData.update({dataAxis: np.round(accSptrmEnvelope*0.707, 4)})
                else:
                    singleDeviceData.update({dataAxis:np.round(accSptrmEnvelope, 4)})

                singleDeviceData.update({"max": max(singleDeviceData[dataAxis])})
                singleDeviceData.update({
                            "signal_processing_details":{
                                            "sampling_frequency": singleDeviceData.get("fs"), "no_of_samples": singleDeviceData.get('no_of_samples'), \
                                                "high_pass": singleDeviceData.get('high_pass'), "low_pass": singleDeviceData.get('low_pass'), "rpm": singleDeviceData.get('rpm')
                                                }
                                            })
                singleDeviceData.update({"x_axis_spectrum_data":f_env.round(4)})
                # pdb.set_trace()

                return Response(singleDeviceData,status=status.HTTP_200_OK)

        except:
            return Response({'message':'Something is wrong with the data. Please contact admin.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(singleDeviceData,status=status.HTTP_200_OK)

@api_view(['POST'])
def getAcousticSpectrum(request):
    if request.method == 'POST':
        print("---------Using New Spectrum Api---------")
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': "Json Data not found."}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            excitation_voltage = 3.3
            n = 12
            composite = data.get("composite_key")
            sensor_type, mac, asset_id, mount_id = composite.split("_")
            dataTimestamp = data.get("timestamp")

            if dataTimestamp:
                try:
                    utc_dt = datetime.utcfromtimestamp(dataTimestamp).replace(tzinfo=pytz.utc)
                    local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
                except:
                    return Response({'message': "Unable to convert timestamp."}, status=status.HTTP_404_NOT_FOUND)
                data.update({'timestamp': local_dt})
            
            # For old MAC addresses
            if mac in ["CC:7B:5C:37:0C:14", "D1:0C:8A:94:22:5D"]:
                ADC_MAX = 4095
                VREF = 3.3
                ZERO_G_VOLTAGE = VREF / 2
                SENSITIVITY = 0.05
                
                try:
                    acousticRawData = models.RawDataMaster.objects.filter(
                        composite__endswith=mount_id, 
                        timestamp=data.get("timestamp"), 
                        axis="a"
                    ).first()
                except Exception as e:
                    return Response({'message': "Spectrum not found."}, status=status.HTTP_200_OK)
                
                if not acousticRawData:
                    return Response({'message': "Spectrum not found."}, status=status.HTTP_200_OK)
                
                rData = acousticRawData.raw_data
                
                df_processed = []
                for i in rData:
                    voltage = float(i) * (VREF / ADC_MAX)
                    accel_g = (voltage - ZERO_G_VOLTAGE) / SENSITIVITY
                    df_processed.append(round(float(accel_g), 4))
                
                df_processed = np.array(df_processed)
                df_processed = df_processed - np.mean(df_processed)

                df_fft, f = getFFT(df_processed, acousticRawData.fs)
                
                final_data = {
                    "composite": composite,
                    "timestamp": data.get("timestamp"),
                    "twf_data": df_processed.tolist(),
                    "spectrum_data": np.round(df_fft, 3).tolist(),
                    "spectrum_data_10k": np.round(df_fft, 3).tolist(),
                    "spectrum_data_20k": [],
                    "frequency_data": np.round(f, 3).tolist(),
                    "frequency_data_10k": np.round(f, 3).tolist(),
                    "frequency_data_20k": [],
                    "asset_id": asset_id,
                    "axis": "a"
                }
                
                if composite in ['ble_FD:A4:C8:32:9C:EB_67178104a58fd75e0c74a440_3723',
                                'ble_FF:4B:4F:9C:E4:34_67178104a58fd75e0c74a440_3724',
                                'ble_D9:72:23:F0:78:C2_67178104a58fd75e0c74a440_3725',
                                'ble_FE:90:0C:2E:BC:C9_67178104a58fd75e0c74a440_3726']:
                    final_data['frequency_data_10k'] = []
                    final_data['spectrum_data_10k'] = []
                
                return Response({"data": final_data}, status=status.HTTP_200_OK)
            
            # For regular sensors
            else:
                try:
                    # Get raw acoustic data
                    if sensor_type == 'w':
                        acousticRawData = models.RawDataMaster.objects.filter(
                            composite=composite, 
                            timestamp=data.get("timestamp"), 
                            asset_id=asset_id, 
                            axis='a'
                        ).first()
                    else:
                        acousticRawData = models.RawDataMaster.objects.filter(
                            composite__endswith=mount_id, 
                            timestamp=data.get("timestamp"), 
                            asset_id=asset_id, 
                            axis='a'
                        ).first()
                    
                    if not acousticRawData:
                        return Response({'message': "Raw data not found for this timestamp."}, status=status.HTTP_200_OK)
                    
                    acousticData = acousticRawData.raw_data
                    fs = acousticRawData.fs
                    
                    # Process raw data
                    df = np.array(acousticData[20:], dtype=float)
                    df_processed = df * excitation_voltage / (2 ** n - 1)
                    df_processed = df_processed - np.mean(df_processed)
                    
                    # Calculate FFT for full spectrum
                    df_fft, f = getFFT(df_processed, fs)
                    
                    # 0-10k Hz filter
                    high_10k = 5
                    low_10k = 10000
                    df_filtered_10k = bandPassFilter(df_processed, high_10k, low_10k, fs)
                    fft_filtered_10k, f_10k = getFFT10K(df_filtered_10k, fs)
                    
                    # 20-40k Hz filter
                    high_20k = 20000
                    if composite == "ble_DC:1F:A4:41:18:A7_67138ad485b49a16b2dc738a_3766":
                        low_20k = 75000
                    else:
                        low_20k = 39000
                    
                    df_filtered_20k = bandPassFilter(df_processed, high_20k, low_20k, fs)
                    fft_filtered_20k, f_20k = getFFT20K(df_filtered_20k, fs, high_20k, low_20k)
                    
                    # Create final data response matching AcousticsSpectrumMasterSerializer format
                    final_data = {
                        "composite": composite,
                        "timestamp": data.get("timestamp"),
                        "twf_data": np.round(df_processed, 4).tolist(),
                        "spectrum_data": np.round(df_fft, 3).tolist(),
                        "spectrum_data_10k": np.round(fft_filtered_10k, 3).tolist(),
                        "spectrum_data_20k": np.round(fft_filtered_20k, 3).tolist(),
                        "frequency_data": np.round(f, 3).tolist(),
                        "frequency_data_10k": np.round(f_10k, 3).tolist(),
                        "frequency_data_20k": np.round(f_20k, 3).tolist(),
                        "asset_id": asset_id,
                        "axis": acousticRawData.axis
                    }
                    
                    # Special case handling for certain composites
                    if composite in ['ble_FD:A4:C8:32:9C:EB_67178104a58fd75e0c74a440_3723',
                                    'ble_FF:4B:4F:9C:E4:34_67178104a58fd75e0c74a440_3724',
                                    'ble_D9:72:23:F0:78:C2_67178104a58fd75e0c74a440_3725',
                                    'ble_FE:90:0C:2E:BC:C9_67178104a58fd75e0c74a440_3726']:
                        final_data['frequency_data_10k'] = []
                        final_data['spectrum_data_10k'] = []
                    
                    return Response({"data": final_data}, status=status.HTTP_200_OK)
                
                except Exception as e:
                    print("Error in calculation:", e)
                    return Response({'message': "Error in calculation."}, status=status.HTTP_200_OK)
        
        except Exception as e:
            print("Error:", e)
            return Response({'message': "Spectrum not found."}, status=status.HTTP_200_OK)
