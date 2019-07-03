from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.http import JsonResponse


def liveness(request):
    return JsonResponse({})


def readiness(request):
    try:
        call_command('check')
    except SystemCheckError:
        return JsonResponse({'error': "Django's check command failed"}, status=500)
    return JsonResponse({})
