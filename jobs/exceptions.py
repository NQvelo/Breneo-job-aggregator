from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # Now add the HTTP status code to the response.
    if response is not None:
        response.data['status_code'] = response.status_code
        
        # Standardize error message format if needed
        # Current DRF output: {'detail': '...', ...} or {'field_name': ['...'], ...}
        if 'detail' not in response.data and not isinstance(response.data, list):
            # If it's a validation error with field names
            response.data = {
                'status_code': response.status_code,
                'error': 'Validation Error',
                'details': response.data
            }
        elif 'detail' in response.data:
            response.data = {
                'status_code': response.status_code,
                'error': str(exc.__class__.__name__),
                'message': response.data['detail']
            }

    return response
