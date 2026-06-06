from rest_framework.parsers import JSONParser
from app import models
from app import serializers
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
import json

# Create your views here.

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

@api_view(['POST', ])
def admin_registration_view(request):

    if request.method == 'POST':
        code = request.data.get('code')
        if code:
            if code != 'code123':
                return Response({'message':'Wrong Code provided'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = serializers.AdminRegistrationSerializer(data=request.data)
        data = {}
        if serializer.is_valid():
            account = serializer.save()
            admin_serializer = models.Admin.objects.create(user=account)
            if admin_serializer:
                admin_serializer.save()
            else:
                return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
            data['message'] = 'successfully registered new user.'
            token = Token.objects.get(user=account).key
            data['token'] = token
        else:
            data = {'message':get_error_msg(serializer.errors)}
        return Response(data)

@api_view(['POST', ])
def customer_registration_view(request):

    if request.method == 'POST':
        serializer = serializers.CustomerRegistrationSerializer(data=request.data)
        try:
            role_data = models.RoleMaster.objects.get(id=request.data.get('role'))
        except models.RoleMaster.DoesNotExist:
            return Response({"message":"Role not found"},status=status.HTTP_404_NOT_FOUND)
        try:
            company_data = models.CompanyMaster.objects.get(id=request.data.get('org_id'))
        except models.CompanyMaster.DoesNotExist:
            return Response({"message":"Company not found"},status=status.HTTP_404_NOT_FOUND)
        data = {}
        if serializer.is_valid():
            account = serializer.save()
            customer_serializer = models.Customer.objects.create(user=account,\
                phone=request.data.get('phone_no'),role=role_data,\
                    org_id=company_data)
            if customer_serializer:
                customer_serializer.save()
            else:
                return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
            data['message'] = 'successfully registered new user.'
            token = Token.objects.get(user=account).key
            data['token'] = token
        else:
            data = {'message':get_error_msg(serializer.errors)}
        return Response(data)

@api_view(['POST', ])
def login(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':'No Data Received'}, status=status.HTTP_400_BAD_REQUEST)
        email = data.get('username')
        password = data.get('password')
        try:
            models.Account.objects.get(email=email)
            df = models.Account.objects.get(email=email)
        except models.Account.DoesNotExist:
            return Response({"message":"Email Address not found"},status=status.HTTP_404_NOT_FOUND)
        user = authenticate(email=email, password=password)
        if not user:
            return Response({'message':'Incorrect Password'}, status=status.HTTP_400_BAD_REQUEST)
        print("user details after loginnnnnnnnnnnn", df)
        data = {}
        if user is not None:
            data['message'] = 'successfully logged in.'
            token = Token.objects.get(user=user).key
            data['token'] = token
        else:
            return Response({'message':'Not Authorised'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)

@api_view(['POST', ])
def forgot_password(request):

    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':'No Data Received'}, status=status.HTTP_400_BAD_REQUEST)
        code = data.get('code')
        if code:
            if code != 'code123':
                return Response({'message':'Wrong Code provided'}, status=status.HTTP_400_BAD_REQUEST)
        email = data.get('username')
        password = data.get('password')
        try:
            user = models.Account.objects.get(email=email)
        except models.Account.DoesNotExist:
            return Response({"message":"Email Address not found"},status=status.HTTP_404_NOT_FOUND)
        user.set_password(password)
        user.save()
        token = Token.objects.get(user=user).key

        return Response({'message':'successfully logged in.','token':token})