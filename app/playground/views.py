from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework import status
from app.SPFunctions.fftFunctions import getFFT, FFTAnalysisTwoSide
import numpy as np
from scipy import signal
from scipy.fftpack import fft,ifft, hilbert
from datetime import datetime
import pytz
from app import models
from django.db.models.functions import Extract
local_tz = pytz.timezone("Asia/Kolkata") 
from app import serializers
from django.core.serializers.json import DjangoJSONEncoder
from app.SPFunctions.SignalProcessing import getPeak, peakDetect
import json
import pdb


################# function for signal processing #################


def signalProcessingFunction(data, fs=25600):
    vib_raw = data
    # print("from AVD")
    """Acc twf and spectrum"""
    # pdb.set_trace()
    accelerationTWF = np.array(vib_raw)
    accelerationSptrm, f_acc = getFFT(vib_raw, fs)
    twf = np.linspace(0, (len(data)-1)/fs, (len(data)))

    # if realm == "Acceleration":
    #     return  twf.round(4), f_acc.round(4)
    
    """Velocity twf and spectrum"""
    Y_complex, f_complex = FFTAnalysisTwoSide(accelerationTWF,fs)
    Y_complex_vel = (Y_complex*9.8*1000)/(2*np.pi*(fs/2 - abs(f_complex)))
    
    for i in np.arange(len(Y_complex_vel)):
        if fs/2 - abs(f_complex[i]) <= 3:
            Y_complex_vel[i] = 0
    Y_vel = ifft(Y_complex_vel, len(Y_complex_vel))
    magY_vel = np.real(Y_vel)
    velocityTWF = magY_vel - np.mean(magY_vel)
    velocitySptrm, f_vel = getFFT(velocityTWF, fs)

    # if realm == "Velocity":
    return accelerationTWF.round(4), accelerationSptrm.round(4), velocityTWF.round(4), velocitySptrm.round(4), twf.round(4), f_acc.round(4), f_vel.round(4)
    
    # """Displacement twf and spectrum"""
    # Y_complex_dis = (Y_complex_vel*1000)/(2*np.pi*(fs/2 - abs(f_complex)))
    
    # for i in np.arange(len(Y_complex_dis)):
    #     if fs/2 - abs(f_complex[i]) <= 3:
    #         Y_complex_dis[i] = 0
    # Y_dis = ifft(Y_complex_dis, len(Y_complex_dis))
    # magY_dis = np.real(Y_dis)
    # displacementTWF = magY_dis - np.mean(magY_dis)
    # displacementSptrm, f_dis = getFFT(displacementTWF, fs)
    
    # if realm == "Displacement":
    #     return  displacementTWF.round(4), displacementSptrm.round(4),  f_dis.round(4), twf.round(4)

def omegaArithmetic(data, fs=25600):
    vib_raw = data
    # print("from AVD")
    """Acc twf and spectrum"""
    # pdb.set_trace()
    accelerationTWF = np.array(vib_raw)
    accelerationSptrm, f_acc = getFFT(vib_raw, fs)
    twf = np.linspace(0, (len(data)-1)/fs, (len(data)))

    return accelerationTWF.round(4), accelerationSptrm.round(4), f_acc.round(4), twf.round(4)



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


############### use GMT time against timestamp to extract raw data ###############

@api_view(['GET','POST'])
def process_envelope_spectrum_data(request):
    if request.method == 'POST':
            
        # try:
            # pdb.set_trace()
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            print("data receivedddddddddddd", data)
            timestamp = data.get("timestamp")
            axis = data.get('axis')
            compositeKey = data.get('composite_key')
            high_pass_filter = data.get('high', 0)
            low_pass_filter = data.get('low', 8000)
            if high_pass_filter == None:
                 high_pass_filter = 0
            if low_pass_filter == None:
                 low_pass_filter = 3000
            # rpm = data.get("rpm")
            final_data = {}
            try:
                utc_dt = datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
            except:
                return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)

            rawData = models.RawDataMaster.objects.filter(timestamp=utc_dt, axis=axis, composite=compositeKey).values()
            fs = rawData[0].get("fs")
            string_list = rawData[0].get("raw_data")
            raw_data = [float(element) for element in string_list]

            vibrationDataRaw = np.multiply(raw_data, 0.9)

            vibrationDataUnFiltered = vibrationDataRaw - np.mean(vibrationDataRaw)
            vibrationData = bandPassFilter(vibrationDataUnFiltered,high_pass_filter,low_pass_filter, fs)
            envelopeVibrationData = getEnvelope(vibrationData)


            accelerationTWF, accelerationSptrm, f_acc, twf = omegaArithmetic(envelopeVibrationData,int(fs))
            
            final_data.update({"timestamp": timestamp, "fs": fs, "high": high_pass_filter, "low": low_pass_filter, "acc_env_sptrm": accelerationSptrm, "acc_env_freq":f_acc })



            return Response({'data': final_data}, status=status.HTTP_200_OK)



@api_view(['GET','POST'])
def PlayScreenAPI(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

            axis_list = data.get("axis_list")
            composite_key = data.get('mac_id')
            dataTimestamp = data.get('timestamp')
            high_pass = data.get("high_pass")
            low_pass = data.get("low_pass")
            rpm = data.get("rpm")
            bpfo = data.get("bpfo")
            bpfi = data.get("bpfi")
            bsf = data.get("bsf")
            ftf = data.get("ftf")

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
        
        
        singleDeviceData = {}

        try:
            old_flow = False
            # **************************************************** Getting raw data for processing ****************************************************

            raw_data_object = models.RawDataMaster.objects.filter(composite=composite_key,timestamp=data.get('timestamp'), axis__in = axis_list)
            raw_data_serializer = serializers.RawDataMasterSerializer(raw_data_object, many=True)
            if len(raw_data_serializer.data) == 0:
                old_flow = True
                mappingDict =  {
                    "horizontal":{"X": "Axial", "Y": "Vertical", "Z": "Horizontal"},
                    "vertical": {"X": "Horizontal", "Y": "Axial", "Z": "Vertical"},
                    "axial": {"X": "Horizontal", "Y": "Vertical", "Z": "Axial" }
                    }
                device_data = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                sensorOrientation = device_data.mount_direction
                deviceMapping = mappingDict.get(sensorOrientation)
                matching_axis = [key for key, value in deviceMapping.items() if value in axis_list]
                print("matching_axismatching_axis", matching_axis)
                raw_data_object = models.RawDataMaster.objects.filter(composite=composite_key,timestamp=data.get('timestamp'), axis__in = matching_axis)
                raw_data_serializer = serializers.RawDataMasterSerializer(raw_data_object, many=True)
                if len(raw_data_serializer.data) == 0:
                    deviceMapping = {key.lower(): value for key, value in deviceMapping.items()}
                    matching_axis = [key.lower() for key, value in deviceMapping.items() if value in axis_list]
                    raw_data_object = models.RawDataMaster.objects.filter(composite=composite_key,timestamp=data.get('timestamp'), axis__in = matching_axis)
                    raw_data_serializer = serializers.RawDataMasterSerializer(raw_data_object, many=True)
            else :
                old_flow = False
            processedDataObject = []
            for jsondata in raw_data_serializer.data:
                samplingFrequency = jsondata['fs']
                rData = jsondata['raw_data']
                rData = [float(i) for i in rData]

                vibrationDataRawSignal = np.multiply(rData, 0.87)

                # *************************************** Band Pass Filter ***************************************
                if high_pass == None and low_pass == None:
                    signal_processing_data = models.SignalProcessingMaster.objects.filter(composite_id=composite_key).values('high_pass','low_pass')
                    try:
                        highPass = int(signal_processing_data[0].get("high_pass"))
                    except:
                        highPass = 10
                    try:
                        lowPass = int(signal_processing_data[0].get("low_pass"))
                    except:
                        lowPass = 6000
                else:
                    highPass = high_pass
                    lowPass = low_pass
                
                try:
                    vibrationDataUnFiltered = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)
                    vibrationData = bandPassFilter(vibrationDataUnFiltered,highPass,lowPass,samplingFrequency)
                except:
                    vibrationData = vibrationDataRawSignal - np.mean(vibrationDataRawSignal)

                # *************************************** Acceleration Envelope ***************************************
                try:
                    accTwfEnvelope = getEnvelope(vibrationData)
                    accSptrmEnvelope, accSptrmF = getFFT(accTwfEnvelope, samplingFrequency)
                except:
                    accTwfEnvelope = []
                    accSptrmEnvelope = []

                # *************************************** Acceleration Velocity Spectrum ***************************************
                Atwf, Asptrm, Vtwf, Vsptrm, xtwf, xsptrm, vel_xsptrm = signalProcessingFunction(vibrationData, samplingFrequency)

                if old_flow:
                    processedDataObject.append({'_id':composite_key, 'timestamp':dataTimestamp, 'axis': deviceMapping.get(jsondata['axis']), \
                                            'Atwf': Atwf, 'Asptrm': Asptrm, 'Vsptrm': Vsptrm, 'envelope': accSptrmEnvelope.round(4), 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})
                else:
                    processedDataObject.append({'_id':composite_key, 'timestamp':dataTimestamp, 'axis': jsondata['axis'], \
                                            'Atwf': Atwf, 'Asptrm': Asptrm, 'Vsptrm': Vsptrm, 'envelope': accSptrmEnvelope.round(4), 'no_of_samples':jsondata['no_of_samples'], 'fs':jsondata['fs']})

                singleDeviceData.update({"signal": processedDataObject,'xtwf': xtwf, 'xsptrm': xsptrm,})

                # ********************************** Acceleration Spectrum Bearing Fault Frequencies **********************************
                bff_data_acc = {}
                bearingData = {"bpfo": bpfo,"bpfi": bpfi,"bsf": bsf,"ftf": ftf}
                # pdb.set_trace()
                try:
                    for faultFrequency in ['bpfo','bpfi','bsf','ftf']:
                        f_acc = np.array(xsptrm)
                        # peaks_acc = []
                        # peak_frequence_acc = []
                        acc_df = []
                        row_acc = len(Asptrm)*2
                        if bearingData.get(faultFrequency):
                            BFF = float(bearingData.get(faultFrequency)) * (rpm/60)
                            # BFF = float(bearingData.get(faultFrequency))
                            # BFF = float(bearingData.get(faultFrequency)) * rpm


                            for index in range(1,6,1):
                                try:
                                    if index in [1,2]:
                                        f_desired = (f_acc>=(BFF*(index)-2*(samplingFrequency/row_acc))) & (f_acc<=(BFF*(index)+2*(samplingFrequency/row_acc)))
                                    elif index in [3,4]:
                                        f_desired = (f_acc>=(BFF*(index)-3*(samplingFrequency/row_acc))) & (f_acc<=(BFF*(index)+3*(samplingFrequency/row_acc)))
                                    else:
                                        f_desired = (f_acc>=(BFF*(index)-(samplingFrequency/row_acc))) & (f_acc<=(BFF*(index)+(samplingFrequency/row_acc)))
                                    acc_peak, acc_peak_axis = peakDetect(Asptrm,f_acc,f_desired)
                                    # peaks_acc.append(round(float(acc_peak),3))
                                    peak_value_index = np.where(f_acc == acc_peak_axis)
                                    # peak_frequence_acc.append(peak_value_index[0][0])
                                    acc_df.append([peak_value_index[0][0], round(float(acc_peak),3)])
                                    # bff_data_acc.update({faultFrequency+"_amp": peaks_acc, faultFrequency+"_freq": peak_frequence_acc})
                                except:
                                    pass
                            bff_data_acc.update({faultFrequency: acc_df})
                        else:
                            bff_data_acc.update({faultFrequency: acc_df})
                except:
                    bff_data_acc.update({faultFrequency: acc_df})


                # ********************************** Acceleration Envelope Spectrum Bearing Fault Frequencies **********************************
                bff_data_env = {}
                try:
                    for faultFrequency in ['bpfo','bpfi','bsf','ftf']:
                        f_env = np.array(accSptrmF)
                        env_sptrm_df = []
                        row_env_sptrm = len(accSptrmEnvelope)*2
                        if bearingData.get(faultFrequency):
                            BFF = float(bearingData.get(faultFrequency)) * (rpm/60)
                            # BFF = float(bearingData.get(faultFrequency))
                            # BFF = float(bearingData.get(faultFrequency)) * rpm


                            for index in range(1,6,1):
                                try:
                                    if index in [1,2]:
                                        f_desired = (f_env>=(BFF*(index)-2*(samplingFrequency/row_env_sptrm))) & (f_env<=(BFF*(index)+2*(samplingFrequency/row_env_sptrm)))
                                    elif index in [3,4]:
                                        f_desired = (f_env>=(BFF*(index)-3*(samplingFrequency/row_env_sptrm))) & (f_env<=(BFF*(index)+3*(samplingFrequency/row_env_sptrm)))
                                    else:
                                        f_desired = (f_env>=(BFF*(index)-(samplingFrequency/row_env_sptrm))) & (f_env<=(BFF*(index)+(samplingFrequency/row_env_sptrm)))
                                    env_peak, env_peak_axis = peakDetect(accSptrmEnvelope,f_env,f_desired)
                                    # peaks_vel.append(round(float(vel_peak),3))
                                    peak_value_index = np.where(f_env == env_peak_axis)
                                    # peak_frequence_acc.append(peak_value_index[0][0])
                                    env_sptrm_df.append([peak_value_index[0][0], round(float(env_peak),3)])
                                    # bff_data_vel.update({faultFrequency+"_amp": peaks_acc, faultFrequency+"_freq": peak_frequence_acc})
                                except:
                                    pass
                            bff_data_env.update({faultFrequency: env_sptrm_df})
                        else:
                             bff_data_env.update({faultFrequency: env_sptrm_df})
                except:
                     bff_data_env.update({faultFrequency: env_sptrm_df})



                # ********************************** Velocity Spectrum Bearing Fault Frequencies **********************************
                bff_data_vel = {}
                try:
                    for faultFrequency in ['bpfo','bpfi','bsf','ftf']:
                        f_vel = np.array(vel_xsptrm)
                        # peaks_vel = []
                        # peak_frequence_acc = []
                        vel_df = []
                        row_vel = len(Vsptrm)*2
                        if bearingData.get(faultFrequency):
                            if faultFrequency == 'bsf':
                                BFF = float(bearingData.get(faultFrequency)) * (rpm/60) * 2
                            else:
                                BFF = float(bearingData.get(faultFrequency)) * (rpm/60)
                            # BFF = float(bearingData.get(faultFrequency)) * rpm

                            for index in range(1,6,1):
                                try:
                                    if index in [1,2]:
                                        f_desired = (f_vel>=(BFF*(index)-2*(samplingFrequency/row_vel))) & (f_vel<=(BFF*(index)+2*(samplingFrequency/row_vel)))
                                    elif index in [3,4]:
                                        f_desired = (f_vel>=(BFF*(index)-3*(samplingFrequency/row_vel))) & (f_vel<=(BFF*(index)+3*(samplingFrequency/row_vel)))
                                    else:
                                        f_desired = (f_vel>=(BFF*(index)-(samplingFrequency/row_vel))) & (f_vel<=(BFF*(index)+(samplingFrequency/row_vel)))
                                    vel_peak, vel_peak_axis = peakDetect(Vsptrm,f_vel,f_desired)
                                    # peaks_vel.append(round(float(vel_peak),3))
                                    peak_value_index = np.where(f_vel == vel_peak_axis)
                                    # peak_frequence_acc.append(peak_value_index[0][0])
                                    vel_df.append([peak_value_index[0][0], round(float(vel_peak),3)])
                                    # bff_data_vel.update({faultFrequency+"_amp": peaks_acc, faultFrequency+"_freq": peak_frequence_acc})
                                except:
                                    pass
                            bff_data_vel.update({faultFrequency: vel_df})
                        else:
                             bff_data_vel.update({faultFrequency: vel_df})
                except:
                     bff_data_vel.update({faultFrequency: vel_df})


            return Response({'data': singleDeviceData, 'acc_bff': bff_data_acc, 'vel_bff':bff_data_vel, 'env_bff': bff_data_env}, status=status.HTTP_200_OK)

        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def GetConfig(request):
    if request.method == 'POST':
        try:
            # pdb.set_trace()
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

            composite_key = data.get("composite_key")
            mountForeignKey = composite_key.split("_")[-1]
            finalData = {"composite_key":composite_key, "mountForeignKey":mountForeignKey}


            try:
                signalData = models.SignalProcessingMaster.objects.get(mount=mountForeignKey)
                high_pass = signalData.high_pass
                low_pass = signalData.low_pass
                rpm = signalData.rpm
                finalData.update({'signal_processing':{"high_pass":high_pass,"low_pass":low_pass,"rpm":rpm}})
            except:
                jsondata = {"high_pass":None,"low_pass":None,"rpm":""}
                finalData.update({'signal_processing':jsondata})

            try:
                bearingData = models.BearingDetailMaster.objects.get(mount=mountForeignKey)
                bearingDataSerializer = serializers.BearingDetailMasterSerializer(bearingData)
                jsondataStr = json.dumps(bearingDataSerializer.data, cls=DjangoJSONEncoder)
                jsondata = json.loads(jsondataStr)
                del jsondata['asset_id']

                finalData.update({'bearing_details':jsondata})
            except:
                jsondata = {'bpfo':None, 'bpfi':None, 'bsf':None, 'ftf':None, 'bearing_number':None}
                finalData.update({'bearing_details':jsondata})


            return Response(finalData, status=status.HTTP_200_OK)
            

        except:
            return Response({'message':"Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)










