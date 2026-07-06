from django.contrib import admin

from .models import (
    AccountStatement,
    BusinessProfile,
    ClientProfile,
    CustomerOwner,
    PendingCalendarEvent,
    VaccinationRecord,
    Visit,
    VisitSeries,
    TimelineMediaAsset,
    VisitTimelineEvent,
)


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'main_phone', 'business_email', 'updated_at')
    readonly_fields = ('singleton_key', 'updated_at')


class VaccinationRecordInline(admin.TabularInline):
    model = VaccinationRecord
    extra = 0
    fields = ('received_at', 'expires_at', 'papers_received', 'validated', 'vet_clinic', 'vaccination_details')


@admin.register(CustomerOwner)
class CustomerOwnerAdmin(admin.ModelAdmin):
    list_display = (
        'owner_name', 'owner_email', 'coi_confirmed_received', 'coi_sent_at',
    )
    list_filter = ('coi_confirmed_received',)
    search_fields = ('owner_name', 'owner_email')
    readonly_fields = ('coi_sent_at', 'coi_confirmed_at')


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = (
        'dog_name', 'owner_name', 'owner_email', 'pipeline_stage', 'approved_at',
    )
    list_filter = ('pipeline_stage',)
    search_fields = ('dog_name', 'owner_name', 'owner_email')
    inlines = [VaccinationRecordInline]


@admin.register(VaccinationRecord)
class VaccinationRecordAdmin(admin.ModelAdmin):
    list_display = ('client', 'expires_at', 'received_at', 'papers_received', 'validated', 'vet_clinic')
    list_filter = ('validated', 'papers_received')
    search_fields = ('client__dog_name', 'client__owner_name', 'vet_clinic')
    raw_id_fields = ('client',)


@admin.register(VisitSeries)
class VisitSeriesAdmin(admin.ModelAdmin):
    list_display = (
        'client', 'frequency', 'interval', 'total_occurrences', 'end_type', 'created_at',
    )
    list_filter = ('frequency', 'end_type')
    search_fields = ('client__dog_name', 'client__owner_name')
    raw_id_fields = ('client',)


@admin.register(TimelineMediaAsset)
class TimelineMediaAssetAdmin(admin.ModelAdmin):
    list_display = (
        'media_type', 'captured_at', 'original_visit', 'latitude', 'longitude',
    )
    list_filter = ('media_type', 'location_used_fallback')
    search_fields = ('caption_notes', 'original_visit__client__dog_name')
    readonly_fields = (
        'media_type', 'photo_high_res', 'photo_thumbnail', 'video_file', 'caption_notes',
        'latitude', 'longitude', 'location_used_fallback', 'location_fallback_label',
        'captured_at', 'original_visit',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(VisitTimelineEvent)
class VisitTimelineEventAdmin(admin.ModelAdmin):
    list_display = ('visit', 'media_asset', 'shared_at', 'source_event')
    search_fields = ('visit__client__dog_name', 'media_asset__caption_notes')
    readonly_fields = ('visit', 'media_asset', 'source_event', 'shared_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = (
        'client', 'scheduled_start', 'scheduled_end', 'status',
        'series', 'series_position', 'calculated_fee',
    )
    list_filter = ('status',)
    search_fields = ('client__dog_name', 'client__owner_name')
    raw_id_fields = ('client', 'cloned_from', 'series')


@admin.register(PendingCalendarEvent)
class PendingCalendarEventAdmin(admin.ModelAdmin):
    list_display = ('summary', 'start_datetime', 'matched_client', 'review_status')
    list_filter = ('review_status',)
    search_fields = ('summary', 'description')


@admin.register(AccountStatement)
class AccountStatementAdmin(admin.ModelAdmin):
    list_display = ('client', 'week_start', 'week_end', 'total_amount', 'send_status', 'sent_at')
    list_filter = ('send_status',)
    readonly_fields = ('line_items',)