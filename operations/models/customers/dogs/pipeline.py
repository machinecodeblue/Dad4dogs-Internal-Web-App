from django.db import models
from django.utils import timezone


class DogPipelineMixin:
    """Intake pipeline stages, stay readiness gates, and advancement actions."""

    class PipelineStage(models.TextChoices):
        INQUIRY = 'inquiry', 'Inquiry'
        MEET_GREET = 'meet_greet', 'Meet & Greet'
        EVALUATION = 'evaluation', 'Evaluation'
        APPROVED = 'approved', 'Approved Repeat Client'

    def standard_stay_blockers(self) -> list[str]:
        blockers = []
        if self.is_hidden:
            blockers.append(
                f'{self.dog_name} is hidden from the client list and cannot be booked for a new stay.'
            )
        if self.pipeline_stage != self.PipelineStage.APPROVED:
            blockers.append(
                f'{self.dog_name} is still in {self.get_pipeline_stage_display()}. '
                f'Standard stays require Approved.'
            )
        if not self.has_current_vaccination:
            blockers.append(
                f'{self.dog_name} has no current validated vaccination.'
            )
        owner = self.customer_owner
        if not owner.coi_confirmed_received:
            blockers.append(
                f'COI has not been confirmed for {owner.owner_name}.'
            )
        return blockers

    def evaluation_stay_blockers(self) -> list[str]:
        """Block Initial Evaluation booking until M&G Passed + paperwork ready."""
        from operations.services.pipeline import dog_has_passed_meet_greet

        blockers = []
        if self.is_hidden:
            blockers.append(
                f'{self.dog_name} is hidden from the client list and cannot be booked.'
            )
        if self.pipeline_stage != self.PipelineStage.EVALUATION:
            blockers.append(
                f'{self.dog_name} must be in Evaluation (Pass Meet & Greet first). '
                f'Currently {self.get_pipeline_stage_display()}.'
            )
        if not dog_has_passed_meet_greet(self):
            blockers.append(
                f'Pass a completed Meet & Greet for {self.dog_name} before Initial Evaluation.'
            )
        if not self.has_current_vaccination:
            blockers.append(
                f'{self.dog_name} needs a current validated vaccination before Evaluation.'
            )
        owner = self.customer_owner
        if not owner.coi_confirmed_received:
            blockers.append(
                f'Confirm COI for {owner.owner_name} before Initial Evaluation.'
            )
        return blockers

    def can_schedule_meet_greet(self) -> bool:
        return (
            not self.is_hidden
            and self.pipeline_stage in (
                self.PipelineStage.INQUIRY,
                self.PipelineStage.MEET_GREET,
            )
        )

    def advance_pipeline(self) -> bool:
        order = [
            self.PipelineStage.INQUIRY,
            self.PipelineStage.MEET_GREET,
            self.PipelineStage.EVALUATION,
            self.PipelineStage.APPROVED,
        ]
        try:
            idx = order.index(self.pipeline_stage)
        except ValueError:
            return False
        if idx >= len(order) - 1:
            return False
        self.pipeline_stage = order[idx + 1]
        if self.pipeline_stage == self.PipelineStage.APPROVED:
            self.approved_at = timezone.now()
        self.save()
        return True
