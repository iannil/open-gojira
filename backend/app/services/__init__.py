from app.core.observability_instrument import instrument_module

instrument_module(
    "app.services",
    exclude=["seed_*", "builtin_seeder"],
)
