"""Stdout summary helpers for seed_demo_data."""

from __future__ import annotations

from collections import Counter

from operations.models import ClientProfile, CustomerOwner, Visit
from operations.services.demo_seed.owners_dogs import SeedBundle


def format_seed_summary(bundle: SeedBundle, visit_counts: dict[str, int]) -> str:
    stage_counts = Counter(s.dog.pipeline_stage for s in bundle.dogs)
    lines = [
        'Demo seed complete',
        f'  Owners: {CustomerOwner.objects.count()} (expected 25)',
        f'  Dogs:   {ClientProfile.objects.count()} (expected 30)',
        f'  Visits: {Visit.objects.count()}',
        '',
        'Pipeline stages:',
    ]
    for stage, label in ClientProfile.PipelineStage.choices:
        lines.append(f'  {label}: {stage_counts.get(stage, 0)}')
    lines.append('')
    lines.append('Visit scenarios:')
    for key, value in visit_counts.items():
        lines.append(f'  {key}: {value}')
    lines.append('')
    lines.append('Scenario tags (dogs):')
    for seed in bundle.dogs:
        hidden = ' [hidden]' if seed.dog.is_hidden else ''
        lines.append(f'  {seed.dog.dog_name} — {seed.scenario}{hidden}')
    return '\n'.join(lines)
