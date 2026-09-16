# SKYGUARD Edge Subsystem

## Responsibilities

The edge subsystem contains the embedded firmware and ingestion adapters for physical microcontroller hardware testbeds (ESP32 + BME280 sensor suite).

## System Role & Testbed Scope

> [!NOTE]
> **Demonstration Testbed, Not a Hard Dependency**:
> Physical edge hardware serves as an end-to-end data acquisition demonstration testbed to prove real-world hardware integration and telemetry streaming. The SKYGUARD decision engine operates independently of whether data originates from physical microcontrollers, synthetic networks, or government telemetry feeds.

## Planned Components (To Be Implemented in M3)

- `firmware/`: MicroPython / C++ Arduino firmware for ESP32 with BME280 (temperature, relative humidity, pressure).
- `bridge/`: Local serial/MQTT gateway daemon forwarding observations to the SKYGUARD backend ingestion endpoint.
