"""Pipeline / intake progression helpers (Meet & Greet → Evaluation → Approved)."""

from django.core.exceptions import ValidationError
from django.utils import timezone

MEET_GREET_SLUG = 'meet_greet'
INITIAL_EVALUATION_SLUG = 'initial_evaluation'

PIPELINE_ORDER = ('inquiry', 'meet_greet', 'evaluation', 'approved')


def dog_has_passed_meet_greet(dog) -> bool:
    """True when a completed M&G visit was explicitly Passed (not merely checked out)."""
    return dog.visits.filter(
        status='completed',
        business_service__slug=MEET_GREET_SLUG,
        meet_greet_outcome='pass',
    ).exists()


def dog_has_completed_meet_greet(dog) -> bool:
    """Backward-compatible name — means Passed Meet & Greet."""
    return dog_has_passed_meet_greet(dog)


def dog_has_meet_greet_visit(dog) -> bool:
    """Any non-cancelled M&G visit on file (scheduled, checked in, or completed)."""
    return dog.visits.filter(
        business_service__slug=MEET_GREET_SLUG,
    ).exclude(status='cancelled').exists()


def pending_meet_greet_outcome_visit(dog):
    """Latest completed M&G still needing Pass/Decline."""
    return (
        dog.visits.filter(
            status='completed',
            business_service__slug=MEET_GREET_SLUG,
            meet_greet_outcome='',
        )
        .order_by('-actual_departure', '-scheduled_end')
        .first()
    )


def pending_evaluation_outcome_visit(dog):
    return (
        dog.visits.filter(
            status='completed',
            business_service__slug=INITIAL_EVALUATION_SLUG,
            evaluation_outcome='',
        )
        .order_by('-actual_departure', '-scheduled_end')
        .first()
    )


def intake_pipeline_context(dog, customer_owner) -> dict:
    """UI context for the dog-detail intake workflow board."""
    from operations.models import ClientProfile

    stage = dog.pipeline_stage
    has_mg = dog_has_meet_greet_visit(dog)
    pending_mg = pending_meet_greet_outcome_visit(dog)
    pending_eval = pending_evaluation_outcome_visit(dog)
    eval_blockers = dog.evaluation_stay_blockers()
    can_eval = not eval_blockers
    can_standard = not dog.standard_stay_blockers()
    can_mg = dog.can_schedule_meet_greet()

    steps = [
        {'key': 'meet_greet', 'label': '1. Meet & Greet', 'active': stage in ('inquiry', 'meet_greet')},
        {'key': 'paperwork', 'label': '2. Paperwork', 'active': stage == 'evaluation' and not can_eval},
        {'key': 'evaluation', 'label': '3. Evaluation', 'active': stage == 'evaluation' and can_eval},
        {'key': 'approved', 'label': '4. Approved', 'active': stage == 'approved'},
    ]

    primary = None
    status_line = dog.get_pipeline_stage_display()

    if pending_mg:
        primary = {
            'kind': 'link',
            'label': 'Record Meet & Greet outcome',
            'url_name': 'operations:meet_greet_outcome',
            'url_pk': pending_mg.pk,
        }
        status_line = 'Meet & Greet completed — record Pass or Decline'
    elif pending_eval:
        primary = {
            'kind': 'link',
            'label': 'Record evaluation outcome',
            'url_name': 'operations:evaluation_outcome',
            'url_pk': pending_eval.pk,
        }
        status_line = 'Initial Evaluation completed — record outcome'
    elif can_mg and (stage in ('inquiry', 'meet_greet')):
        primary = {
            'kind': 'link',
            'label': 'Schedule Meet & Greet',
            'url_name': 'operations:schedule_meet_greet',
            'url_pk': dog.pk,
            'query': '',
            'hint': '15 minutes · $0 · one-off intake appointment',
        }
        if stage == 'meet_greet' and not has_mg:
            status_line = 'Meet & Greet required — no appointment on file yet'
        elif stage == 'inquiry':
            status_line = 'Inquiry — schedule Meet & Greet to begin'
        else:
            status_line = 'Meet & Greet — schedule or complete the appointment'
    elif stage == 'evaluation' and not can_eval:
        primary = {
            'kind': 'paperwork',
            'label': 'Complete paperwork',
        }
        status_line = 'Evaluation track — vaccination and COI required before booking'
    elif can_eval:
        primary = {
            'kind': 'link',
            'label': 'Schedule Initial Evaluation',
            'url_name': 'operations:schedule_evaluation',
            'url_pk': dog.pk,
            'query': '',
            'hint': '4 hours · $15 · one-off intake appointment',
        }
        status_line = 'Ready for Initial Evaluation'
    elif can_standard:
        primary = {
            'kind': 'link',
            'label': 'Schedule stay',
            'url_name': 'operations:visit_create',
            'url_pk': dog.pk,
            'query': '',
        }
        status_line = 'Approved — book standard stays'

    vax_status = dog.vaccination_status
    vax_label = {
        'missing': 'No record on file',
        'expired': 'Expired',
        'expiring': 'Expiring soon',
        'ok': 'Current',
    }.get(vax_status, vax_status)

    return {
        'steps': steps,
        'status_line': status_line,
        'primary': primary,
        'evaluation_blockers': eval_blockers,
        'can_schedule_meet_greet': can_mg,
        'can_schedule_evaluation': can_eval,
        'can_schedule_standard': can_standard,
        'has_meet_greet_visit': has_mg,
        'stale_meet_greet_stage': stage == 'meet_greet' and not has_mg,
        'vax_status': vax_status,
        'vax_label': vax_label,
        'coi_received': bool(customer_owner.coi_confirmed_received),
        'coi_status': customer_owner.coi_status,
        'can_revert': stage != ClientProfile.PipelineStage.INQUIRY,
    }


def apply_meet_greet_outcome(visit, *, outcome: str, notes: str) -> None:
    """Record M&G Pass/Decline; Pass advances dog to Evaluation track."""
    from operations.models import ClientProfile, Visit

    notes = (notes or '').strip()
    if not notes:
        raise ValidationError('Enter notes about the Meet & Greet.')
    if outcome not in Visit.MeetGreetOutcome.values:
        raise ValidationError('Choose Pass or Decline.')
    if not visit.is_meet_greet_visit:
        raise ValidationError('Outcomes apply only to Meet & Greet visits.')
    if visit.status != Visit.Status.COMPLETED:
        raise ValidationError('Check out the Meet & Greet before recording an outcome.')
    if visit.meet_greet_outcome:
        raise ValidationError('An outcome was already recorded for this Meet & Greet.')

    visit.meet_greet_outcome = outcome
    visit.meet_greet_notes = notes
    visit.save(update_fields=['meet_greet_outcome', 'meet_greet_notes', 'updated_at'])

    dog = visit.client
    if outcome == Visit.MeetGreetOutcome.PASS:
        dog.pipeline_stage = ClientProfile.PipelineStage.EVALUATION
        dog.save(update_fields=['pipeline_stage', 'updated_at'])


def pass_meet_greet(dog) -> None:
    raise ValidationError(
        f'Record Pass or Decline on {dog.dog_name}\'s Meet & Greet visit '
        f'(check-out redirects to the outcome form).',
    )


def apply_evaluation_outcome(visit, *, outcome: str, notes: str) -> None:
    """Record evaluation outcome and apply pipeline effects for Approve."""
    from operations.models import ClientProfile, Visit

    notes = (notes or '').strip()
    if not notes:
        raise ValidationError('Enter notes on how the dog did and the outcome.')
    if outcome not in Visit.EvaluationOutcome.values:
        raise ValidationError('Choose Approve, Reject, or Recommend further evaluation.')
    if not visit.is_evaluation_visit:
        raise ValidationError('Outcomes apply only to Initial Evaluation visits.')
    if visit.status != Visit.Status.COMPLETED:
        raise ValidationError('Check out the evaluation visit before recording an outcome.')
    if visit.evaluation_outcome:
        raise ValidationError('An outcome was already recorded for this evaluation.')

    visit.evaluation_outcome = outcome
    visit.evaluation_notes = notes
    visit.save(update_fields=['evaluation_outcome', 'evaluation_notes', 'updated_at'])

    dog = visit.client
    if outcome == Visit.EvaluationOutcome.APPROVE:
        dog.pipeline_stage = ClientProfile.PipelineStage.APPROVED
        dog.approved_at = timezone.now()
        dog.save(update_fields=['pipeline_stage', 'approved_at', 'updated_at'])


def revert_pipeline_stage(dog) -> str:
    """Roll back one pipeline step. Does not delete visits or outcomes."""
    from operations.models import ClientProfile

    order = [
        ClientProfile.PipelineStage.INQUIRY,
        ClientProfile.PipelineStage.MEET_GREET,
        ClientProfile.PipelineStage.EVALUATION,
        ClientProfile.PipelineStage.APPROVED,
    ]
    try:
        idx = order.index(dog.pipeline_stage)
    except ValueError as exc:
        raise ValidationError('Unknown pipeline stage.') from exc
    if idx == 0:
        raise ValidationError(f'{dog.dog_name} is already at Inquiry.')
    previous = order[idx - 1]
    dog.pipeline_stage = previous
    update_fields = ['pipeline_stage', 'updated_at']
    if previous != ClientProfile.PipelineStage.APPROVED:
        dog.approved_at = None
        update_fields.append('approved_at')
    dog.save(update_fields=update_fields)
    return dog.get_pipeline_stage_display()
