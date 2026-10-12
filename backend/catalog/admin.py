from django.contrib import admin

from .models import ContentReport, Publication, TakedownRequest


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "status", "license", "requested_at", "reviewed_by")
    list_filter = ("status", "license")
    search_fields = ("course__title", "attribution")


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "node", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("course__title", "reason")


@admin.register(TakedownRequest)
class TakedownRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "name", "email", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("course__title", "name", "email", "details")
