from rest_framework.views import exception_handler

def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF that returns errors in a consistent format:
    {
        "status": False,
        "message": ...,
        "data": ...  # error details
    }
    """
    response = exception_handler(exc, context)
    if response is not None:
        data = response.data
        # Try to provide a useful message
        if isinstance(data, dict) and "detail" in data:
            message = data["detail"]
        elif isinstance(data, dict):
            # Use first error message if available
            first_error = next(iter(data.values()), None)
            if isinstance(first_error, list) and first_error:
                message = str(first_error[0])
            else:
                message = "Validation Error"
        else:
            message = "Validation Error"
        response.data = {
            "status": False,
            "message": message,
            "data": data
        }
    return response

from rest_framework.response import Response

def custom_response(success=True, message="", data=None, status_code=200):
    return Response({
        "status": success,
        "message": message,
        "data": data
    }, status=status_code)