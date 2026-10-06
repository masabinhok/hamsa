# 0004. Models propose, a deterministic router decides, a human approves

- Status: Accepted
- Date: 2026-10-06

## Context
A model's verdict and self-reported confidence are not calibrated, and an LLM deciding its own next step (an "agent loop") is hard to test and hard to explain to a checker. Yet the product's value is that the AI's output changes what happens next: merge duplicates, fast-track clear cases, escalate unclear ones. The cost of errors is asymmetric: a confidently wrong fast-track is far worse than an unnecessary human review.

## Options considered
- **LLM agent chooses the route.** Flexible, but untestable and non-deterministic.
- **Route on model confidence alone.** Simple, but uncalibrated.
- **Rules over model outputs plus deterministic signals,** with thresholds tuned on the eval set.

## Decision
The router is a pure function of stage outputs, with ordered rules, each returning a route and the reasons that fired. Fast-track requires agreement between the model verdict and an independent deterministic signal (archive hit, two or more independent sources). Nothing is published without a checker's approval.

## Consequences
- The router is unit-tested exhaustively, and every route is explainable on the desk.
- Thresholds are tuned for fast-track precision of 0.95 or more, which sends more cases to humans. That trade is deliberate.
- New signals mean new rules, not prompt changes.
