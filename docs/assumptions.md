# Assumptions and Scope Notes

## Assumptions
- Input files are JSON documents that follow the structure represented by the sample data.
- The project is intended as a local or demo-grade implementation rather than a production-scale enterprise platform.
- SQLite is sufficient for storage during evaluation and review.
- Normalisation rules are driven by the JSON files in the config folder and may need adjustment for broader real-world datasets.

## Constraints
- The current implementation focuses on the documented sample format and the core pipeline features requested for the review exercise.
- The UI is intended for operational review and not as a full patient-record management system.
- Authentication, role-based access, and multi-user concurrency are not part of the current scope.

## Review considerations
- The repository should be evaluated based on clarity, reproducibility, architecture traceability, and ability to run locally.
- The architecture diagram and notes should be enough to explain the solution in a short presentation or walkthrough.
