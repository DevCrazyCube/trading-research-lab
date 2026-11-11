"""Factory strategy library (builder B2, DESIGN_v2 §3.7 / §4 / §5 / §6).

    from scripts.factory.strategies import registry, common

    for universe, cols in registry.universes(panel).items():        # FX: G10 and G10EM; else ALL
        sub = panel.subset(cols)
        for rule in registry.rules(lane, sub):                      # enabled rules the panel can run
            signal = rule.fn(sub, **rule.params)                    # raw signal in [-1, 1], NaN = no view
            w = common.size_positions(signal, sub, registry.sigma_target(lane))
        for rule, why in registry.not_applicable(lane, sub):        # ledger these as NOT APPLICABLE
            ...

Modules: `common` (causal building blocks), `rules_trend`, `rules_carry`, `rules_value`, `rules_xs`,
`rules_reversal`, `rules_misc` (VOL / SEASON / SKEW / XASSET / FLOW), `rules_ml`, `registry`.
Nothing in this package imports the engine, the statistics or the data layer; the only dependency inside
the factory is `panel.PanelBundle`.
"""
from . import common, registry
from .common import NotApplicable, size_positions
from .registry import (ALL_RULES, PrimarySpec, Rule, declared_counts, disabled_rules, fx_universes,
                       grid_manifest, grid_sha256, not_applicable, primaries, primary_members, rules,
                       sigma_target, universes)

__all__ = ["ALL_RULES", "NotApplicable", "PrimarySpec", "Rule", "common", "declared_counts", "disabled_rules",
           "fx_universes", "grid_manifest", "grid_sha256", "not_applicable", "primaries", "primary_members",
           "registry", "rules", "sigma_target", "size_positions", "universes"]
