# C13.5 Live ETABS Geometry Source Lock

Status: PARTIAL_SOURCE_LOCKED

## Component type source

Table: Frame Assignments - Summary

Live row count: 998

API columns:
Story, Label, UniqueName, Type, Length, AutoSelect, AnalysisSect, DesignSect, AxisAngle, MaxStaSpcg, MinNumSta, Releases, UserOffsets, AddedMass, Pier, Spandrel, Spring, Modifiers, TCLimits, MomentBeam

Locked mapping:
- join_key: UniqueName
- component_type_column: Type
- Beam -> beam
- Column -> column
- Brace / Null -> unsupported

Note:
- Excel/display column may appear as Design Type.
- Live ETABS API column is Type.

## Section assignment source

Table: Frame Assignments - Section Properties

Live row count: 998

API columns:
Story, Label, UniqueName, Shape, AutoSelect, SectProp

Locked mapping:
- join_key: UniqueName
- section_property_column: SectProp

## Concrete rectangular geometry source

Table: Frame Section Property Definitions - Concrete Rectangular

Live row count: 16

API columns:
Name, Material, FromFile, FileName, SectInFile, t3, t2, RigidZone, NotSizeType, NotAutoFact, NotUserSize, DesignType, AMod, A2Mod, A3Mod, JMod, I2Mod, I3Mod, MMod, WMod, Color, GUID, Notes

Locked mapping:
- section_key_column: Name
- width_column: t2
- depth_column: t3
- design_type_column: DesignType

Observed raw geometry values:
- t2 raw type: str
- t2 examples: 0.3, 0.4, 0.5, 0.6
- t3 raw type: str
- t3 examples: 0.5, 0.6, 0.7, 0.87, 1, 1.3, 1.5

## Live ETABS units

GetPresentUnits_2 raw: [4, 6, 2, 0]
GetDatabaseUnits_2 raw: [4, 6, 2, 0]

Locked unit mapping:
- force_enum 4 -> kN
- length_enum 6 -> m
- temperature_enum 2 -> C
- return_code 0 -> OK

## P6.2 decision

P6.2 may parse numeric strings such as "0.4" into observed numeric values.

P6.2 may normalize from m to mm only with preserved evidence:
- raw_value
- raw_value_type
- source_table
- source_column
- source_unit: m
- normalized_value
- normalized_unit: mm
- normalization_basis: ETABS GetPresentUnits_2 and GetDatabaseUnits_2

Still forbidden:
- section name parsing
- dimension guessing
- unit conversion without ETABS unit evidence
- engineering OK/FAIL checks in feature provider
