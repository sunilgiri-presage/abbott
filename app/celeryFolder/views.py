from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from time import sleep
from datetime import datetime
from app.task import sleepy


@api_view(['GET'])
def WithoutCelery(request):
    if request.method == 'GET':
        print("here in without celery")
        t1 = datetime.now()
        sleep(5)
        t2 = datetime.now()
        print("sending response after ", t2-t1)
        return Response({'message': 'Response from without celery'}, status=status.HTTP_200_OK)
    
@api_view(['GET'])
def WithCelery(request):
    if request.method == 'GET':
        print("here in with celery")
        t1 = datetime.now()
        sleepy.delay(5)
        t2 = datetime.now()
        print("sending response after ", t2-t1)
        return Response({'message': 'Response from with celery'}, status=status.HTTP_200_OK)