# Public fabric secret wiring correction

The repository already has the trusted environment `pfarma-ci-trusted`, used by the existing hosted private-source workflows. The super-factory execute job omitted the environment binding, so environment-scoped secrets were unavailable and `PRIVATE_REPO_TOKEN` resolved to an empty string.

The correction adds `environment: pfarma-ci-trusted` to the execute job. No token rotation or secret reconfiguration is required.
