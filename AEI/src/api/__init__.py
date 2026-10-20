"""
AEI — FastAPI Integration Layer
=================================
Exposes the AEI evacuation-planning pipeline as an HTTP API that the
mobile React Native app can call directly.

Sub-modules
-----------
models       — Pydantic request/response models (mirror of mobile api.ts)
plan_builder — assembles the EvacuationPlan response from existing modules
main         — FastAPI application with all four endpoints

Endpoints
---------
GET  /health             — liveness probe
POST /plan               — compute a full evacuation plan for a location
POST /plan/replan        — simulate a road blockage and replan
POST /plan/replan/clear  — remove the simulated blockage, restore baseline

Version: 0.1.0  (matches CONTRACT_VERSION in integration/schemas.py)
"""
