from django.contrib import admin

from .models import (
    Asset,
    AssetCustomField,
    AssetCustomFieldName,
    AssetGroup,
    AssetTag,
    Attachment,
    Group,
    Scan,
    Tag,
    ViperWebhookJob,
)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    pass


@admin.register(AssetCustomFieldName)
class AssetCustomFieldNameAdmin(admin.ModelAdmin):
    pass


@admin.register(AssetCustomField)
class AssetCustomFieldAdmin(admin.ModelAdmin):
    pass


@admin.register(AssetGroup)
class AssetGroupAdmin(admin.ModelAdmin):
    pass


@admin.register(AssetTag)
class AssetTagAdmin(admin.ModelAdmin):
    pass


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    pass


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    pass


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    pass


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    pass


@admin.register(ViperWebhookJob)
class ViperWebhookJobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "callback", "since", "before", "created_at")
    list_filter = ("status",)
    readonly_fields = (
        "id",
        "created_at",
        "callback",
        "since",
        "before",
        "request_body",
        "status",
    )
