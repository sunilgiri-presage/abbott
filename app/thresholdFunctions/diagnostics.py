from app import models, serializers
from rest_framework.views import APIView
from django.db.models import DateTimeField
from django.db.models.functions import Trunc
from django.core.mail import send_mail
from datetime import datetime, date, timedelta
from django.template.loader import render_to_string, get_template
from django.core.mail import send_mail, EmailMessage, EmailMultiAlternatives
import requests
import string
import random
import json
import base64
import pdb
import pytz
ist_timezone = pytz.timezone('Asia/Kolkata')
utc_timezone = pytz.timezone('UTC')

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


def insert_missing_multiples(data, tolerance=5):
    base = data[0]
    result = []
    zero_indices = []
    for i in range(1, 11):
        expected_value = base * i
        # Check if there's a number in data within tolerance of expected_value
        if any(abs(val - expected_value) <= tolerance for val in data):
            result.append(next(val for val in data if abs(val - expected_value) <= tolerance))
        else:
            result.append(0)
            zero_indices.append(i-1)  # Subtract 1 because list indices start at 0
    return result, zero_indices

def insert_zeros_amp(data, indices):
    for index in indices:
        if index <= len(data):
            data.insert(index, 0)
        else:
            pass
    return data


statfunctionList = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'four_to_seven']


# class CalculateCounterForDiagnostics(APIView):
def CalculateCounterForDiagnostics():
    # pdb.set_trace()
    dataToCheck = models.DiagnosticsValuesMaster.objects.filter(flag=False).order_by("timestamp")

    allThresholdValues = models.DiagnosticsDynamicThresholdValuesMaster.objects.all()

    allCounterValues = models.DiagnosticThresholdCounterMaster.objects.all()

    if len(dataToCheck) > 0:
        for single_row in dataToCheck:
            try:
                # print("single_rowsingle_rowsingle_row", single_row.timestamp)
                singleThresh = allThresholdValues.get(composite=single_row.composite, axis=single_row.axis)
                counterObject = allCounterValues.get(composite=single_row.composite, axis=single_row.axis)
                for statFunction in statfunctionList:
                    try:

                        # updating level 3 counter, else updating counter as 0
                        if getattr(singleThresh, statFunction+"_amp_level_3") > 0 and getattr(single_row, statFunction+"_amp") >= getattr(singleThresh, statFunction+"_amp_level_3"):
                            counter = getattr(counterObject, statFunction + '_amp_counter_level_3')
                            updatedCounter = counter + 1
                            setattr(counterObject, statFunction +'_amp_counter_level_3', updatedCounter)
                            counterObject.save()
                        else:   
                            setattr(counterObject, statFunction + '_amp_counter_level_3', 0)
                            counterObject.save()

                        # updating level 2 counter, else updating counter as 0
                        if getattr(singleThresh, statFunction+"_amp_level_2") > 0 and getattr(singleThresh, statFunction+"_amp_level_3") > getattr(single_row, statFunction+"_amp") >= getattr(singleThresh, statFunction+"_amp_level_2"):
                            counter = getattr(counterObject, statFunction + '_amp_counter_level_2')
                            updatedCounter = counter + 1
                            setattr(counterObject, statFunction +'_amp_counter_level_2', updatedCounter)
                            counterObject.save()
                        else:
                            setattr(counterObject, statFunction + '_amp_counter_level_2', 0)
                            counterObject.save()

                        # updating level 1 counter, else updating counter as 0
                        if getattr(singleThresh, statFunction+"_amp_level_1") > 0 and getattr(singleThresh, statFunction+"_amp_level_2") > getattr(single_row, statFunction+"_amp") >= getattr(singleThresh, statFunction+"_amp_level_1"):
                            counter = getattr(counterObject, statFunction + '_amp_counter_level_1')
                            updatedCounter = counter + 1
                            setattr(counterObject, statFunction +'_amp_counter_level_1', updatedCounter)
                            counterObject.save()
                        else:
                            setattr(counterObject, statFunction + '_amp_counter_level_1', 0)
                            counterObject.save()
                    except:
                        pass

                # diagnosticSingleData = models.DiagnosticsValuesMaster.objects.get(id=single_row.id)
                # updateData = {'flag': True}
                # print("diagnosticSingleDatadiagnosticSingleDatadiagnosticSingleData", diagnosticSingleData.flag)
                single_row.flag = True
                single_row.save()
                # diagnosticSingleData.flag = True
                # diagnosticSingleData.save()

                # diagnosticSingleDataSerializer = serializers.DiagnosticsValuesMasterSerializer(instance=diagnosticSingleData, data=updateData, partial=True)
                # if diagnosticSingleDataSerializer.is_valid():
                #     print("diagnosticSingleDataSerializer good")
                #     diagnosticSingleDataSerializer.save()
                # else:
                #     print("diagnosticSingleDataSerializer not good")
            except:
                pass
    else:
        pass

def sendMailSingle(alarmHistoryData, apiData):
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
        url = "https://cua119013p.oneabbott.com/cmms/redirect?key="           # live url

        user_data = json.dumps({
            "componenet": "assets/asset-analyze/",
            "asset_id": alarmHistoryData.get("asset_id"),
            "token": single_user.get("token"),
            "id": single_user.get("id")})
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

        if alarmHistoryData.get("priority") == "Critical":
            html_message = render_to_string(
                'fault_temp/critical.html', {'data': final_data})
        elif alarmHistoryData.get("priority") == "Danger":
            html_message = render_to_string(
                'fault_temp/danger.html', {'data': final_data})
        elif alarmHistoryData.get("priority") == "Alert":
            html_message = render_to_string(
                'fault_temp/alert.html', {'data': final_data})

        mail_sending_time = datetime.now(pytz.UTC).astimezone(country_tz).strftime("%m-%d-%Y, %I:%M:%S %p")
        subject = 'Sensor Alerts: '+'   '+final_data.get("location")+' > '+final_data.get("asset_name")+' ('+str(mail_sending_time)+' )'
        message = ''
        email_from = "Sensor-Alerts<no-reply@oneabbott.ai>"  # put abbott email name here
        # recipient_list = ["k.preetsid@gmail.com"]
        recipient_list = [single_user.get("email")]
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body='',
                from_email=email_from,
                to=recipient_list,
                reply_to=['no-reply@oneabbott.ai']  # put abbott email name here
            )

            email.attach_alternative(html_message, "text/html")
            email.content_subtype = 'html'
            email.mixed_subtype = 'related'
            res = email.send(fail_silently=False)
            # print("mail sent to", single_user.get("email"))
        except:
            print("--------------------------mail not sent something wrong--------------------------")

    return True




def checkAllLevelCounterDiagnostics(row, func, level):

    """
    row is single instance of diagnostic_threshold_counter_master table
    func is function like one, two...etc
    """
    if level == '1':
        priority = "Alert"
    elif level == '2':
        priority = "Danger"
    elif level == '3':
        priority = "Critical"

    existingAlarm = models.AlarmHistoryMaster.objects.annotate(truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
                                                                       ).filter(truncated_date__date=date.today(), priority=priority, composite = row.get("composite"), fault_flag=True)
    if len(existingAlarm) == 0:    #checking if single mail is being sent on same day

        if (row.get(func+'_amp_counter_level_'+level) >= row.get(func+'_amp_repetition_level_'+level)) and row.get(func+'_amp_counter_level_'+level) > 0:
            updateCount = {func+'_amp_counter_level_'+level: 0}
            single_row = models.DiagnosticThresholdCounterMaster.objects.get(
                id=row.get('id'))
            threshold_counter_serializer = serializers.DiagnosticThresholdCounterMasterSerializer(
                instance=single_row, data=updateCount, partial=True)
            deviceMountData = models.DeviceMountMaster.objects.get(
                composite_id=row.get("composite"))

            statData = models.DiagnosticsValuesMaster.objects.filter(
                composite=row.get("composite"), axis=row.get("axis")).latest('timestamp')
            timestamp = statData.timestamp
            value = getattr(statData, func+"_amp")

            setThresholdValue = models.DiagnosticsDynamicThresholdValuesMaster.objects.get(composite=row.get("composite"),
                                                                signal_type=row.get("signal_type"), axis=row.get("axis"))
            threshValue = getattr(setThresholdValue, func+"_amp_level_"+level)

            sensorAxis = row.get("axis")

            if func == "one":
                fault_type = "Structural Looseness/Unbalance"
            elif func == "two":
                fault_type = "Misalignment"
            elif func == "four_to_seven":
                fault_type = "Rotating Looseness"
            else:
                fault_type = "Fault"
            
            alarmHistoryData = {"composite": deviceMountData.composite_id, "signal_type": fault_type, "trend_type": "detected_", "axis": sensorAxis, "priority": priority,
                                "sensor_location": deviceMountData.point_name+'-'+deviceMountData.mount_location, "asset_id": deviceMountData.asset_id,
                                "timestamp": timestamp, "threshold_value": threshValue, "observed_value": value, 'fault_flag': True}
            alarmHistoryDataSerializer = serializers.DiagnosticAlarmHistoryMasterSerializer(data=alarmHistoryData)

            try:
                if threshold_counter_serializer.is_valid():
                    if alarmHistoryDataSerializer.is_valid():
                        threshold_counter_serializer.save()
                        alarmHistoryDataSerializer.save()
            except:
                pass

            # url = "http://localhost:3000/api/asset_master/get_user_against_asset?asset_id=" + alarmHistoryData.get("asset_id")
            url = "https://cua119013p.oneabbott.com/cmms_api/api/asset_master/get_user_against_asset?asset_id=" +  alarmHistoryData.get("asset_id")

            res = requests.get(url)
            if res.json().get("message") == 'success':
                apiData = res.json().get("data")
                # existingAlarm = models.AlarmHistoryMaster.objects.annotate(truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
                #                                                         ).filter(truncated_date__date=date.today(), priority=priority, composite = deviceMountData.composite_id)
                # print("existing alarm found for priority", priority, existingAlarm)
                # existingAlarm = models.AlarmHistoryMaster.objects.filter(composite = alarmHistoryData.get("composite")).order_by("creation_date")
                # if len(existingAlarm) > 0:
                #     for i in existingAlarm:
                #         print("iiiiiiiii", i.priority, i.composite)
                #     pass
                # else:
                try:
                    sendMailSingle(alarmHistoryData, apiData)

                except:
                    pass

                # try:
                #     sendmessage(alarmHistoryData, apiData)
                # except:
                #     print("in except of message")
                #     pass
            # else:
            #     print("some error occured while getting user_against_asset_api",
            #         res.json(), " asset_id= ", alarmHistoryData.get("asset_id"))


    return True



# class checkDiagnosticThresholdCounter(APIView):
def checkDiagnosticThresholdCounter():

    # def checkDiagnosticThresholdCounter():
    threshCounter = models.DiagnosticThresholdCounterMaster.objects.all().values()
    for row in threshCounter:
        for func in statfunctionList:
            if row.get(func+'_amp_counter_level_3') != 0:
                checkAllLevelCounterDiagnostics(row, func, '3')
            if row.get(func+'_amp_counter_level_2') != 0:
                checkAllLevelCounterDiagnostics(row, func, '2')
            if row.get(func+'_amp_counter_level_1') != 0:
                checkAllLevelCounterDiagnostics(row, func, '1')
    return True

