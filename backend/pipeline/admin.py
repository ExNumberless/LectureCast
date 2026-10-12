from django.contrib import admin

from .models import PipelineRun, SectionEdit, StageNode, StageRun


@admin.register(StageNode)
class StageNodeAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "stage", "lecture", "status", "frozen", "updated_at")
    list_filter = ("stage", "status", "frozen")
    search_fields = ("course__title", "lecture__title", "error")


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "requested_by", "status", "created_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("course__title", "requested_by__email", "error")


@admin.register(StageRun)
class StageRunAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "node", "status", "started_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("node__course__title", "error")


@admin.register(SectionEdit)
class SectionEditAdmin(admin.ModelAdmin):
    list_display = ("id", "node", "n", "edited_by", "edited_at")
    search_fields = ("node__course__title", "edited_by__email")
