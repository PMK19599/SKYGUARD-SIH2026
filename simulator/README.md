# SKYGUARD Simulator Subsystem

## Responsibilities

The simulator subsystem models a virtual network of Automatic Weather Stations (AWS) subjected to realistic micro-climates, regional weather phenomena, and controlled sensor anomalies.

## Scenario Injection Principles

1. **Pipeline Transparency**: Injected anomalies (e.g., stuck thermistors, drift, sudden pressure spikes) travel through the identical ingestion pipeline as real telemetry.
2. **Strict Ground-Truth Isolation**: Scenario labels and ground-truth metadata are logged separately for evaluation and must **NEVER** leak directly to the decision engine.

## Planned Scenarios (To Be Implemented in M1)

- **Nominal Weather**: Diurnal cycle with solar warming and evening cooling across all stations (`NORMAL`).
- **Cold Front / Squall Line**: Rapid temperature drop and pressure jump propagating realistically across the station grid (`WORLD`).
- **Failing Thermistor**: Gradual upward sensor drift or stuck reading on one station while neighbors report normal trends (`SENSOR`).
- **Lightning Strike / Storm Surge with Sensor Failure**: Storm event accompanied by sensor circuit latch-up or corrupt telemetry (`BOTH`).
- **Sparse Network / Gateway Stale Data**: Insufficient neighbor density or packet delay creating unresolvable uncertainty (`UNKNOWN`).
