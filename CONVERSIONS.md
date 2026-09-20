# Conversions and update review — 17 September 2026

## Reproduced distance failure

The actual Echo Home pipeline request `Convert 5.5km to miles` selected
`echo-experience__echo_convert` with `from_unit=km`, `to_unit=mile`, `value=5.5`.
The converter already supported lengths, but its aliases included `mi` and `miles`
without singular `mile`. That rejected the request. The model then tried
`basic-utilities__unit_convert`, which supports kitchen units, not length.

Version 0.3.1 accepts the missing singular names and US/UK spelling variants for
metric lengths, yards and miles. Unit whitespace and underscores are normalised.
5.5 kilometres equals 3.4175415573 miles, displayed as 3.4175 miles. The Echo agent
continues to use its own deterministic converter so results appear on its screen.

Live text-pipeline verification after deployment passed both `Convert 5.5km to miles`
and `Convert one mile to kilometres`, using only `echo-experience__echo_convert`.
The first returned approximately 3.42 miles in speech text; the second returned
1.609344 kilometres. All 32 Python tests and 11 frontend assertions passed.
The refreshed answer and conversion layouts were checked on the physical Echo.

## Current Echo converter coverage

| Category | Supported | Useful additions to consider |
| --- | --- | --- |
| Distance/length | mm, cm, m, km, inches, feet, yards, miles | Compound heights such as 5 ft 10 in |
| Mass/weight | mg, g, kg, ounces, pounds | Stone and pounds; tonnes |
| Liquid volume | mL, L, UK/US pints and fluid ounces, metric/US cups | cL/dL, teaspoons/tablespoons and UK/US gallons |
| Temperature | Celsius, Fahrenheit, Kelvin | Oven gas marks require an approximate reference table |
| Time | Not currently implemented | Seconds, minutes, hours, days |
| Speed/area | Not currently implemented | mph/km/h and square feet/square metres |
| Energy/pressure | Not currently implemented | kWh/kJ/kcal and bar/psi/kPa |
| Currency | No live rate tool connected | Requires dated exchange-rate data; not a fixed conversion |

For kitchen measures, distinguish metric, US and Australian tablespoon/cup sizes
instead of silently choosing a standard. Ingredient volume-to-weight conversions
need an ingredient-specific density/source; the current converter rejects them.
The most useful next additions for this household are spoons/cL/dL, stone/pounds,
then speed and energy. They are proposals, not implemented in 0.3.1.

## Tools for Assist release review

Installed and running: **1.9.0**. Latest stable: **1.10.2**. The installed converter
was compared byte-for-byte with the 1.10.2 file: it is unchanged. It supports volume,
weight (including stone), and Celsius/Fahrenheit; it does not support distances.
Its kitchen volume constants use US pint/cup/gallon sizes without UK variants.

- [1.10.0](https://github.com/skye-harris/llm_intents/releases/tag/1.10.0), 5 September: new Entity History tool, Home Control disabled-tool enumeration improvements, integration icon.
- [1.10.1](https://github.com/skye-harris/llm_intents/releases/tag/1.10.1), 6 September: restrict history access to exposed entities, better filtering for duplicate names, improved Home Control prompt quoting.
- [1.10.2](https://github.com/skye-harris/llm_intents/releases/tag/1.10.2), 8 September: numeric history deltas and HACS default-list preparation.

The earlier 1.8.3 release already added decilitres and temperature conversions.
Upgrading is useful for the history features/fixes but does not resolve distance
conversion. The upstream integration was not upgraded during this check.

## Why the update was not shown

HACS 2.0.5 is the current stable HACS release. Tools for Assist is registered as a
**custom repository**. Its persisted metadata had last been fetched on **28 August
2026 at 06:48 UTC**, still listing 1.9.0 as latest. It was not pinned; HACS was running,
not disabled, with no pending queue tasks.

A supported `hacs/repository/refresh` call immediately discovered 1.10.2 and changed
`update.tools_for_assist_update` to `on` with installed=1.9.0 and latest=1.10.2. The
update is now visible in HACS and Home Assistant.

The installed HACS source schedules custom-repository checks every **48 hours**;
it does not perform that custom-repository task immediately at startup. Restarts
before the interval elapses can postpone it. This is a possible mechanism for stale
metadata, especially during development; the historical cause of the entire
20-day gap is not proven. Refreshing fixed the observed update visibility.

Source: [HACS 2.0.5 background tasks](https://github.com/hacs/integration/blob/2.0.5/custom_components/hacs/base.py).
For a future stale entry, refresh its update information in HACS; this checks
releases without installing them.

Echo Experience itself is a separate repository. Since 0.6.0 it installs as a single HACS custom repository (or by manual copy of a release archive); before that it was deployed directly with a script. Commits alone do not create a Home Assistant update entity; a tagged release does.
