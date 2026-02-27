from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from ninja import NinjaAPI
from apps.users.api import router as users_router
from apps.payments.api import router as payments_router
from apps.loans.api import router as loans_router

api = NinjaAPI(
    title="Saghat API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
api.add_router("/auth", users_router)
api.add_router("/payments", payments_router)
api.add_router("/loans", loans_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
