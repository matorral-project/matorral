from django.apps import apps

from matorral.taskapp.celery import app


@app.task(ignore_result=True)
def do_in_bulk(operation, object_list):
    if operation not in ['delete', 'duplicate']:
        return

    for (app_label, model_name, pk) in object_list:
        Model = apps.get_app_config(app_label).get_model(model_name)

        try:
            obj = Model.objects.get(pk=pk)
        except Model.DoesNotExist:
            continue

        getattr(obj, operation)()
