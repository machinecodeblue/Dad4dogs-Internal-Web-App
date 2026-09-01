from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from operations.models import (
    BusinessService,
    ClientProfile,
    CustomerOwner,
    VaccinationRecord,
)

TZ = ZoneInfo('America/Toronto')


def default_service_pk(slug='overnight_stay'):
    from operations.services.context_tenant import get_active_workspace
    workspace = get_active_workspace()
    service = BusinessService.objects.filter(tenant=workspace, slug=slug).first()
    if service is None:
        service = BusinessService.objects.filter(tenant=workspace, is_active=True).first()
    return service.pk


def ready_for_standard_stay(dog: ClientProfile) -> ClientProfile:
    dog.pipeline_stage = ClientProfile.PipelineStage.APPROVED
    dog.save(update_fields=['pipeline_stage', 'updated_at'])
    CustomerOwner.ensure_for_client(dog).mark_coi_received()
    VaccinationRecord.objects.create(
        client=dog,
        expires_at=timezone.localdate() + timedelta(days=180),
        validated=True,
    )
    return dog


def test_image_file(name='moment.jpg'):
    buffer = BytesIO()
    Image.new('RGB', (1200, 900), color=(34, 139, 34)).save(buffer, format='JPEG')
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type='image/jpeg')