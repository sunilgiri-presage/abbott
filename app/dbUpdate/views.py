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
from rest_framework.decorators import api_view, permission_classes
from django.db.models import DateTimeField
from django.utils.timezone import utc
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.forms.models import model_to_dict
from app.SPFunctions.SignalProcessing import getPeak, omegaArithmetic, getRMS, peakDetect, getEnvelope, getPeak_to_peak, bandPassFilter, StatFunctionsAdjustment, highPassFilter
from app.SPFunctions.fftFunctions import getFFT, FFTAnalysisTwoSide
from app.SPFunctions.EHNR import EHNR
# from app.SPFunctions.kurtosis import fast_kurtogram
from scipy.stats import kurtosis
from app.thresholdFunctions import thresholdFunctions, scoreCalculations
from app.dashboard.process_save_data import saveData
import json
from app.cron import my_daily_task, calculateAssetHealthHistory
from datetime import datetime, timedelta
import pytz
import calendar
from dateutil import parser
import pdb
# import math
import numpy as np
import base64
import threading 
from django.db.models import Q
from django.db.models.functions import Trunc
from django.db.models import  Count, DateField
from django.utils import timezone
from itertools import product
from collections import defaultdict
import asyncio









@api_view(['POST'])
def getMountIds(request):
    if request.method == 'GET':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            sensor_type = data.get("sensor_type")
            mount_direction = data.get("mount_direction")
            mountIds = models.DeviceMountMaster.objects.filter(composite_id__startswith=sensor_type, mount_direction = mount_direction).values("id")
            print("mountIdsmountIdsmountIds", mountIds)
            return Response({'data': "Okay"}, status=status.HTTP_200_OK)
        except:
            return Response({'message':"Kindly provide a device_id"},status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({'message':"Kindly use GET request"},status=status.HTTP_404_NOT_FOUND)



















