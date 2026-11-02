from django.http import HttpResponse
from django.template.loader import render_to_string


class Custom404Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 404 and not getattr(response, "streaming", False):
            content = render_to_string(
                "creataura/404.html",
                request=request,
            )
            return HttpResponse(content, status=404, content_type="text/html; charset=utf-8")
        return response
