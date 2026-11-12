# Autonomous Evacuation Intelligence (AEI)

**Dynamic disaster evacuation planning, adaptive routing, and experimental flood-risk intelligence.**

AEI is a mobile-focused disaster-management prototype that explores how graph-based routing, geographic visualization, and machine learning can support evacuation planning. It demonstrates how routes can be recalculated when simulated hazards or road closures change the available road network.

> **Project status:** Research and demonstration prototype. Routes, hazards, shelter availability, and travel estimates in the mobile scenarios are simulated. **Do not use AEI for real emergency navigation or safety decisions.**

## Overview

During a disaster, the nearest shelter is not always reachable or suitable. Roads may become blocked, hazard zones may intersect possible routes, and facilities may be unavailable. AEI models these constraints in a controlled environment and demonstrates how an evacuation planner can adapt as conditions change.

The project has two distinct components:

1. **Mobile evacuation application:** Interactive maps, simulated disaster scenarios, destination selection, route guidance, and rerouting after road closures.
2. **Flood-risk machine-learning experiment:** A Python regression pipeline that estimates a synthetic `FloodProbability` target and evaluates predictions against a baseline.

The ML model is **not currently connected to live road-level routing**. Mobile route decisions use the scenario's generated road network, hazard geometry, and road attributes.

## Key Features

- **Five disaster scenarios:** Flood, fire, cyclone, earthquake, and landslide.
- **Flexible starting locations:** Device GPS, a selected map point, or a demonstration location.
- **Interactive geographic visualization:** Roads, hazards, candidate destinations, and route overlays.
- **Adaptive pathfinding:** Excludes blocked or hazard-affected road segments and recalculates available paths.
- **Destination evaluation:** Compares reachable shelters or hospitals using scenario-specific eligibility rules.
- **Travel modes:** Walking and driving for shelter routing; ambulance mode for a hospital-focused workflow.
- **Navigation demonstration:** Route preview, foreground guidance, simulated movement, and arrival states.
- **Failure handling:** Clear unavailable-route state when no feasible path remains.
- **SOS information:** Emergency-information view with location-sharing functionality and sample facility details.
- **Local persistence:** Stores prepared scenario information and selected completion records using SQLite.
- **Flood-risk analysis:** Preprocessing, Random Forest regression, baseline comparison, and provisional risk categories.

## Technology Stack

| Area | Technologies |
| --- | --- |
| Mobile application | React Native, Expo, TypeScript |
| Maps and device location | React Native Maps, Expo Location |
| Routing | Graph-based pathfinding in JavaScript/TypeScript |
| Local storage | Expo SQLite |
| Machine learning | Python, pandas, NumPy, scikit-learn |
| Optional experiments | OpenStreetMap/Overpass-based GIS exploration, Python browser demo, FastAPI |

The optional GIS and API experiments are separate from the primary local mobile routing demonstration.

## How It Works

```text
Choose starting location
          |
Select disaster scenario
          |
Generate scenario roads, hazards, and facilities
          |
Filter unusable roads and ineligible destinations
          |
Calculate and preview a feasible route
          |
Start simulated navigation
          |
Road closure or scenario update?
       /        \
     Yes         No
      |           |
Recalculate    Continue
      |           |
Alternative route available?
       /       \
     Yes        No
      |          |
Update route  Show unavailable / SOS information
```

### Routing logic

AEI represents roads as a graph: intersections or endpoints are **nodes**, and road segments are **edges**. Routing checks connectivity and excludes closed or hazard-intersecting segments before comparing feasible paths. If a closure affects the active route, the system attempts to recalculate to the selected destination or find an eligible alternative.

### Flood-risk modeling

The separate Python workflow validates and cleans tabular inputs, prepares features, trains a Random Forest regressor, and compares predictions with a training-mean baseline on held-out synthetic data. The resulting estimates may be mapped to provisional risk categories for experimentation.

**Important:** Evaluation on synthetic data does not establish real-world flood-prediction accuracy.

## Getting Started

### Prerequisites

- Node.js and npm
- A compatible Expo development environment
- Android device or emulator (or another platform supported by the installed project configuration)
- Python 3.11+ for the optional machine-learning workflow

### 1. Get the source code

Download the repository ZIP and extract it, or clone the repository:

```bash
git clone https://github.com/JenanJn/AEI.git
cd AEI
```

### 2. Run the mobile application

Navigate to the folder containing the mobile application's `package.json`, then run:

```bash
npm install
npx expo start
```

Follow the Expo terminal instructions to open the application on a compatible device or emulator. Grant foreground location permission if using GPS-based starts. A manual or demonstration start can be used when location access is unavailable.

> **Repository layout note:** If `package.json` is inside a subfolder, run these commands from that subfolder. Check the included Expo SDK and your device runtime for compatibility.

### 3. Explore the demonstration

1. Select a starting location.
2. Choose a disaster scenario.
3. Review the generated road network, hazard overlay, and available facilities.
4. Select a reachable shelter or hospital and preview the route.
5. Start guidance and simulate a road closure or movement.
6. Observe rerouting, arrival, or the unavailable-route fallback.

### 4. Explore the Python experiment (optional)

Locate the Python experiment directory and its dependency file in the extracted project. If a `requirements.txt` is provided, create an environment and install it:

```bash
python -m venv .venv
```

On Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

Run the training or evaluation entry point documented in that directory. The exact Python command depends on the scripts included in the repository ZIP.

## Model Evaluation

An archived experiment using a synthetic dataset reported the following held-out results:

| Model | MAE | RMSE | R² |
| --- | ---: | ---: | ---: |
| Training-mean baseline | 0.05527 | 0.07093 | Not reported |
| Random Forest | 0.01468 | 0.01760 | 0.93077 |

The recorded split used 160 training rows and 40 test rows. These numbers describe fit to a **synthetic target**, not validated performance on observed floods. Results should only be reproduced or compared using the corresponding saved fixture, preprocessing, and model configuration.

## Current Limitations

- Disaster scenarios, road closures, facility attributes, and navigation movement are simulated.
- The mobile routing demonstration does not consume live emergency alerts or the Python model's risk predictions.
- Synthetic regression metrics cannot establish operational flood forecasting capability.
- Offline basemap downloads and background turn-by-turn navigation are outside the demonstrated scope.
- Real deployment would require verified geographic data, official hazard feeds, reliable shelter capacity information, accessibility checks, and extensive field testing.

## Future Enhancements

- Integrate verified, time-stamped disaster and road-closure feeds.
- Connect validated geographic risk estimates to individual road segments.
- Add authenticated shelter occupancy and availability updates.
- Improve offline support and resilience under weak connectivity.
- Test routing against real-world transport networks and accessibility requirements.
- Validate predictive models using observed, geographically relevant disaster data.

## Project Purpose

AEI demonstrates how mobile development, graph algorithms, geospatial visualization, and data science can be combined to investigate adaptive evacuation planning. Its focus is on **explainable routing behavior, controlled testing, and a clear separation between demonstrated features and future operational capabilities**.

## Disclaimer

AEI is an experimental prototype, **not an emergency response service**. In an actual emergency, follow official warnings, evacuation orders, and directions from local authorities.
