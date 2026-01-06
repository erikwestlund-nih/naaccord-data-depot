from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from depot.storage.temp_files import TemporaryStorage


@csrf_exempt
def upload_temp_file(request):
    if request.method == "POST" and request.FILES.get("file"):
        uploaded_file = request.FILES["file"]
        content = uploaded_file.read().decode("utf-8")
        temp_file = TemporaryStorage("audit", content, suffix=".csv").create()
        return JsonResponse(
            {
                "success": True,
                "temp_file_id": temp_file["db_row"].id,
                "temp_path": str(temp_file["path"]),
            }
        )

    return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)
