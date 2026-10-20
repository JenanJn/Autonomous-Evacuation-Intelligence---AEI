"""
AEI — Risk Engine
==================
Converts AI hazard predictions into validated risk scores and maps them
onto road-network edge weights for the GIS routing module.

Sub-modules
-----------
scoring      — score HazardPredictionRecords → ScoredRiskRecords
               (proxy transformation, category thresholds, provenance)
validation   — validate individual RiskOutputRecords and batches
               (semantic checks, status/value consistency, duplicate policy)
risk_mapper  — map RiskOutputRecords onto road-network edge attributes
"""
