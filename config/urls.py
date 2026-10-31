"""Root URL configuration for ff-consumer."""

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from two_factor.urls import urlpatterns as tf_urls


def home(request):
    """Simple landing page."""
    html = (
        "<!DOCTYPE html>"
        "<html lang='en'><head>"
        "<meta charset='UTF-8'/>"
        "<title>FlavorFind Consumer API</title>"
        "<style>"
        "body{font-family:sans-serif;background:#0f172a;color:#f1f5f9;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}"
        ".card{text-align:center;padding:3rem 2.5rem;background:#1e293b;"
        "border-radius:1rem;border:1px solid #334155;max-width:480px;width:90%}"
        ".dot{display:inline-block;width:10px;height:10px;background:#22c55e;"
        "border-radius:50%;animation:pulse 2s infinite;margin-right:8px}"
        "@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}"
        "h1{color:#f97316;margin-bottom:.5rem}"
        "p{color:#94a3b8;margin-bottom:2rem}"
        ".links{display:flex;gap:.75rem;justify-content:center;flex-wrap:wrap}"
        "a{padding:.5rem 1.25rem;border-radius:.5rem;text-decoration:none;"
        "font-size:.875rem;font-weight:500}"
        ".primary{background:#f97316;color:#fff}"
        ".secondary{background:#1e40af;color:#fff}"
        "</style></head><body>"
        "<div class='card'>"
        "<div style='color:#22c55e;margin-bottom:1rem'>"
        "<span class='dot'></span>Running</div>"
        "<h1>FlavorFind Consumer API</h1>"
        "<p>Serving the website and Android app.</p>"
        "<div class='links'>"
        "<a href='/docs/' class='primary'>API Docs</a>"
        "<a href='/v1/health/' class='secondary'>Health</a>"
        "</div>"
        "</div></body></html>"
    )
    return HttpResponse(html)


urlpatterns = [
    path("", home, name="home"),
    # Two-factor auth login for staff
    path("", include(tf_urls, namespace="two_factor")),
    # Django admin — 2FA mandatory
    path("admin/", admin.site.urls),
    # API v1
    path("v1/", include("apps.api.urls")),
    # OpenAPI schema and docs
    path("v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

# Debug toolbar in dev
from django.conf import settings  # noqa: E402

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
