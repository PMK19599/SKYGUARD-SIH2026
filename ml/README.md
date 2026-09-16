# SKYGUARD Machine Learning Subsystem

## Responsibilities

The ML subsystem develops statistical and machine learning models that extract contextual and spatio-temporal features to generate supporting evidence for the decision engine.

## AI Role & Safety Boundary

> [!NOTE]
> **AI is an Investigator, Not the Final Judge**:
> Machine learning models in SKYGUARD generate hypotheses and evidence (labeled as `SUPPORTED`, `QUALIFIED`, `UNKNOWN`, or `REJECTED`). ML output is fed into the evidence quality and independence evaluation layers. The final operational decision is always issued by the deterministic decision engine.

## Planned Capabilities (To Be Implemented in M4)

- **Spatial Neighbor Regression / Kriging**: Predicting expected station values from surrounding stations to quantify deviation.
- **Multivariate Autoencoders / Isolation Forests**: Detecting subtle multi-sensor correlation breakdowns (e.g., temperature rises while solar radiation drops and humidity stays flat).
- **Evidence Formatting**: Packaging all model outputs into standardized evidence objects with full provenance metadata.
