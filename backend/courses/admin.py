from django.contrib import admin

from .models import Course, Lecture, Slide


class SlideInline(admin.TabularInline):
    model = Slide
    extra = 0
    fields = ("n", "kind", "title", "start_ms", "end_ms")


class LectureInline(admin.TabularInline):
    model = Lecture
    extra = 0
    show_change_link = True
    fields = ("number", "title", "date", "duration_ms")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "provider", "visibility", "updated_at")
    list_filter = ("provider", "visibility")
    search_fields = ("title", "owner__email", "source_url")
    readonly_fields = ("created_at", "updated_at")
    inlines = (LectureInline,)


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "number", "date")
    list_filter = ("course",)
    search_fields = ("title", "course__title")
    inlines = (SlideInline,)


@admin.register(Slide)
class SlideAdmin(admin.ModelAdmin):
    list_display = ("title", "lecture", "n", "kind", "start_ms", "end_ms")
    list_filter = ("kind",)
    search_fields = ("title", "lecture__title", "lecture__course__title")
