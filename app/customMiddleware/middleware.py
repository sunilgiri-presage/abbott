from django.http import JsonResponse
import requests
import json


# url = "http://localhost:3000/api/users/validate_token"  #Local server url
url = "http://10.11.56.13/cmms_api/api/users/validate_token"  #Live server url


def validate_access_token(token, userId):

    payload = json.dumps({
    "user_id": userId
    })
    headers = {
    'Authorization': token,
    'Content-Type': 'application/json'
    }

    r = requests.request("POST", url, headers=headers, data=payload)
    is_auth = r.status_code
    if is_auth == 200:
        return True
    else:
        return False


class TokenAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        print("requestttttttttt", request.headers)
        # print("requestttttttttt", request.user_id)
        access_token = request.headers.get('Authorization', '')
        userId = request.headers.get('user_id', '')
        # print("access_tokenaccess_token", access_token)
        # print("userIduserIduserIduserId", userId)

        # is_valid = validate_access_token(access_token, userId)  # Replace with your validation logic
        # print("is_validis_validis_validis_validis_valid", is_valid)

        # if not is_valid:
            # return JsonResponse({'error': 'Invalid token'}, status=401)

        response = self.get_response(request)
        return response