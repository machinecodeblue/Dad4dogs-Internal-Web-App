"""Build 25 owners and 30 dogs across pipeline / paperwork scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from operations.models import ClientProfile, CustomerOwner, VaccinationRecord
from operations.services.context_tenant import get_active_workspace

FIRST_NAMES = [
    'Alex', 'Jordan', 'Sam', 'Taylor', 'Casey', 'Riley', 'Morgan', 'Quinn',
    'Avery', 'Jamie', 'Cameron', 'Drew', 'Harper', 'Reese', 'Rowan', 'Skyler',
    'Parker', 'Finley', 'Hayden', 'Emerson', 'Kennedy', 'Peyton', 'Sawyer',
    'Blake', 'Charlie',
]
LAST_NAMES = [
    'Nguyen', 'Patel', 'Singh', 'Chen', 'Williams', 'Brown', 'Garcia', 'Martinez',
    'Lee', 'Kim', 'Anderson', 'Thomas', 'Jackson', 'White', 'Harris', 'Clark',
    'Lewis', 'Robinson', 'Walker', 'Young', 'King', 'Wright', 'Lopez', 'Hill',
    'Scott',
]
DOG_NAMES = [
    'Buster', 'Luna', 'Milo', 'Bella', 'Charlie', 'Daisy', 'Max', 'Lucy',
    'Cooper', 'Sadie', 'Buddy', 'Molly', 'Rocky', 'Bailey', 'Teddy', 'Zoe',
    'Duke', 'Lola', 'Bear', 'Penny', 'Ollie', 'Rosie', 'Zeus', 'Coco',
    'Finn', 'Nala', 'Archie', 'Ruby', 'Leo', 'Willow',
]


@dataclass
class SeedDog:
    dog: ClientProfile
    scenario: str


@dataclass
class SeedBundle:
    owners: list[CustomerOwner] = field(default_factory=list)
    dogs: list[SeedDog] = field(default_factory=list)

    def dogs_by_scenario(self, prefix: str) -> list[ClientProfile]:
        return [s.dog for s in self.dogs if s.scenario.startswith(prefix)]

    def approved_ready(self) -> list[ClientProfile]:
        return [
            s.dog for s in self.dogs
            if s.scenario.startswith('approved_ready')
        ]


def _email(index: int) -> str:
    return f'owner{index:02d}@example.test'


def _phone(index: int) -> str:
    return f'519-555-{1000 + index:04d}'


def _apply_coi(owner: CustomerOwner, *, received: bool) -> None:
    if received:
        owner.mark_coi_received()
    else:
        owner.coi_confirmed_received = False
        owner.coi_confirmed_at = None
        owner.coi_sent_at = None
        owner.save(update_fields=[
            'coi_confirmed_received', 'coi_confirmed_at', 'coi_sent_at', 'updated_at',
        ])


def _add_vax(dog: ClientProfile, *, current: bool, validated: bool = True) -> None:
    today = timezone.localdate()
    expires = today + timedelta(days=180) if current else today - timedelta(days=30)
    VaccinationRecord.objects.create(
        client=dog,
        expires_at=expires,
        validated=validated,
        validated_at=timezone.now() if validated else None,
        vet_clinic='Demo Vet Clinic',
        vaccination_details='Rabies + bordetella (demo)',
    )


def _create_owner(
    index: int,
    *,
    rich_address: bool,
    emergency: bool,
) -> CustomerOwner:
    workspace = get_active_workspace()
    first = FIRST_NAMES[(index - 1) % len(FIRST_NAMES)]
    last = LAST_NAMES[(index - 1) % len(LAST_NAMES)]
    owner = CustomerOwner(
        tenant=workspace,
        owner_email=_email(index),
        owner_name=f'{first} {last}',
        owner_salutation='Mx.' if index % 5 == 0 else '',
        owner_phone=_phone(index),
    )
    if rich_address:
        owner.address_street = f'{100 + index} Grey Street'
        owner.address_unit = f'{index}' if index % 3 == 0 else ''
        owner.address_city = 'London'
        owner.address_province = 'ON'
        owner.address_postal_code = f'N6B {index % 10}G{index % 10}'
    if emergency:
        owner.emergency_contact_name = f'Emergency for {first}'
        owner.emergency_contact_phone = f'519-555-{2000 + index:04d}'
        owner.emergency_contact_relationship = 'Neighbor'
        owner.authorized_pickup_names = f'{first} Partner\nFamily Friend'
    owner.save()
    return owner


def _create_dog(
    owner: CustomerOwner,
    dog_name: str,
    *,
    stage: str,
    scenario: str,
    hidden: bool = False,
) -> SeedDog:
    dog = ClientProfile.objects.create(
        tenant=owner.tenant,
        owner_name=owner.owner_name,
        owner_email=owner.owner_email,
        owner_phone=owner.owner_phone,
        dog_name=dog_name,
        pipeline_stage=stage,
        approved_at=timezone.now() if stage == ClientProfile.PipelineStage.APPROVED else None,
        is_hidden=hidden,
        notes=f'Demo scenario: {scenario}',
        vet_clinic_name='Demo Vet Clinic' if stage != ClientProfile.PipelineStage.INQUIRY else '',
    )
    dog.ensure_feed_credentials()
    return SeedDog(dog=dog, scenario=scenario)


def seed_owners_and_dogs() -> SeedBundle:
    """
    Create exactly 25 owners and 30 dogs.

    Layout: owners 01–20 single-dog; owners 21–25 two dogs each.
    """
    bundle = SeedBundle()
    dog_name_i = 0

    def next_dog_name() -> str:
        nonlocal dog_name_i
        name = DOG_NAMES[dog_name_i % len(DOG_NAMES)]
        dog_name_i += 1
        return name

    # --- Owners 1–25 ---
    for i in range(1, 26):
        owner = _create_owner(
            i,
            rich_address=(i <= 15),
            emergency=(i % 4 == 0),
        )
        bundle.owners.append(owner)

    # Scenario recipe: (owner_index, dog_name_or_None, stage, scenario, coi, vax, hidden)
    # 30 dogs total across owners 1–25 (owners 21–25 get two).
    Stage = ClientProfile.PipelineStage
    specs: list[tuple] = []

    # 4 Inquiry (owners 1–4)
    specs.append((1, 'TBD', Stage.INQUIRY, 'inquiry_tbd', False, None, False))
    specs.append((2, None, Stage.INQUIRY, 'inquiry_plain', False, None, False))
    specs.append((3, None, Stage.INQUIRY, 'inquiry_named', True, False, False))  # expired/missing vax
    specs.append((4, None, Stage.INQUIRY, 'inquiry_coi_only', True, None, False))

    # 4 Meet & Greet (owners 5–8)
    specs.append((5, None, Stage.MEET_GREET, 'mg_ready', True, True, False))
    specs.append((6, None, Stage.MEET_GREET, 'mg_no_coi', False, True, False))
    specs.append((7, None, Stage.MEET_GREET, 'mg_no_vax', True, None, False))
    specs.append((8, None, Stage.MEET_GREET, 'mg_blocked_both', False, None, False))

    # 4 Evaluation (owners 9–12) — visits layer adds passed M&G for some
    specs.append((9, None, Stage.EVALUATION, 'eval_ready', True, True, False))
    specs.append((10, None, Stage.EVALUATION, 'eval_ready_2', True, True, False))
    specs.append((11, None, Stage.EVALUATION, 'eval_no_coi', False, True, False))
    specs.append((12, None, Stage.EVALUATION, 'eval_no_vax', True, None, False))

    # 16 Approved: owners 13–20 (8) + 21–25×2 (10) = 18… need 16 approved + adjust
    # Recalculate: inquiry4 + mg4 + eval4 = 12; remaining 18 for approved family.
    # Plan said ~16 approved — use 18 approved among remaining to hit 30 dogs.
    # owners 13–20: 8 single approved
    for oi in range(13, 21):
        specs.append((oi, None, Stage.APPROVED, f'approved_ready_{oi}', True, True, False))

    # owners 21–25: two dogs each (10 dogs)
    # 21: ready + ready
    specs.append((21, None, Stage.APPROVED, 'approved_ready_21a', True, True, False))
    specs.append((21, None, Stage.APPROVED, 'approved_ready_21b', True, True, False))
    # 22: ready + hidden
    specs.append((22, None, Stage.APPROVED, 'approved_ready_22a', True, True, False))
    specs.append((22, None, Stage.APPROVED, 'approved_hidden_22b', True, True, True))
    # 23: ready + no COI (owner-level COI shared — second dog same owner)
    specs.append((23, None, Stage.APPROVED, 'approved_ready_23a', True, True, False))
    specs.append((23, None, Stage.APPROVED, 'approved_expired_vax_23b', True, False, False))
    # 24: two ready (capacity fodder)
    specs.append((24, None, Stage.APPROVED, 'approved_ready_24a', True, True, False))
    specs.append((24, None, Stage.APPROVED, 'approved_ready_24b', True, True, False))
    # 25: ready + no COI household
    specs.append((25, None, Stage.APPROVED, 'approved_no_coi_25a', False, True, False))
    specs.append((25, None, Stage.APPROVED, 'approved_no_coi_25b', False, True, False))

    assert len(specs) == 30, f'expected 30 dog specs, got {len(specs)}'

    # COI is per owner — apply once per owner from first dog's coi flag, then override carefully
    owner_coi: dict[int, bool] = {}
    for owner_index, _name, _stage, scenario, coi, _vax, _hidden in specs:
        # Households that must lack COI
        if 'no_coi' in scenario or scenario in {
            'inquiry_tbd', 'inquiry_plain', 'mg_no_coi', 'mg_blocked_both', 'eval_no_coi',
        }:
            owner_coi[owner_index] = False
        elif owner_index not in owner_coi:
            owner_coi[owner_index] = bool(coi)

    for owner_index, received in owner_coi.items():
        _apply_coi(bundle.owners[owner_index - 1], received=received)

    for owner_index, dog_name, stage, scenario, _coi, vax, hidden in specs:
        owner = bundle.owners[owner_index - 1]
        name = dog_name if dog_name is not None else next_dog_name()
        # Avoid unique (tenant, email, dog_name) clashes for multi-dog homes
        if ClientProfile.objects.filter(
            tenant=owner.tenant,
            owner_email=owner.owner_email,
            dog_name=name,
        ).exists():
            name = f'{name} {owner_index}'
        seed = _create_dog(owner, name, stage=stage, scenario=scenario, hidden=hidden)
        if vax is True:
            _add_vax(seed.dog, current=True)
        elif vax is False:
            _add_vax(seed.dog, current=False)
        # vax is None → no record
        bundle.dogs.append(seed)

    assert len(bundle.owners) == 25
    assert len(bundle.dogs) == 30
    return bundle
