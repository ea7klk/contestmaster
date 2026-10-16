"""Shared validation for ruleset references to administrator-managed catalogs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import BandCatalogItem, ModeCatalogItem
from backend.app.rulesets.schema import RulesetDefinition


def catalog_reference_errors(
    session: Session, definition: RulesetDefinition
) -> list[dict[str, object]]:
    requested = [
        ("band", value)
        for configured in definition.rules
        if configured.rule.kind == "eligibility"
        for value in configured.rule.allowed_bands
    ] + [
        ("mode", value)
        for configured in definition.rules
        if configured.rule.kind == "eligibility"
        for value in configured.rule.allowed_modes
    ]
    if not requested:
        return []
    available = {
        *(
            ("band", item.key)
            for item in session.scalars(
                select(BandCatalogItem).where(BandCatalogItem.is_active.is_(True))
            )
        ),
        *(
            ("mode", item.key)
            for item in session.scalars(
                select(ModeCatalogItem).where(ModeCatalogItem.is_active.is_(True))
            )
        ),
    }
    errors: list[dict[str, object]] = []
    for index, configured in enumerate(definition.rules):
        rule = configured.rule
        if rule.kind != "eligibility":
            continue
        for field, kind, values in (
            ("allowed_bands", "band", rule.allowed_bands),
            ("allowed_modes", "mode", rule.allowed_modes),
        ):
            for value_index, value in enumerate(values):
                if (kind, value) not in available:
                    errors.append(
                        {
                            "path": f"rules[{index}].{field}[{value_index}]",
                            "message": (
                                f"{value} is not an active {kind} in the operating catalog."
                            ),
                        }
                    )
    return errors
