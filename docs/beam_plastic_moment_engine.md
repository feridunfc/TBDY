# Beam Plastic Moment Engine

## Scope

Pure plastic moment capacity kernel.
Single-reinforced rectangular section: given As, compute Mpr.

## Unit Standard

| Quantity | Unit |
|----------|------|
| Length | mm |
| Force | N |
| Moment | kNm |
| Stress | MPa |
| Area | cm² (input), mm² (calculation) |

## Formulas
fs_capacity = steel_overstrength * fyk
a = As * fs_capacity / (alpha * fcd * bw)
c = a / beta
z = d - a / 2
Mpr = As * fs_capacity * z


## Coefficients

| Parameter | Value | Source |
|-----------|-------|--------|
| alpha | 0.85 | TS500 compression block |
| beta | 0.85 | TS500 (c = a / 0.85) |
| steel_overstrength | 1.25 | Capacity design overstrength |

## Output Status

| Status | Meaning |
|--------|---------|
| OK | Valid Mpr computed |
| NO_REINFORCEMENT | As = 0 |
| COMPRESSION_BLOCK_EXCEEDS_SECTION | a >= d, section inadequate |
| INVALID_INPUT | Invalid geometry/material |

## Claim Limitations

- PLASTIC_MOMENT_ENGINE = PROVEN
- FULL_TBDY_CAPACITY_DESIGN_CERTIFIED = FALSE
- Overstrength policy pending code-article benchmark

## Constraints

This kernel:
- Uses no external model adapters
- Does not compute Ve_capacity
- Does not compare provided reinforcement
- Produces no reports or UI output
