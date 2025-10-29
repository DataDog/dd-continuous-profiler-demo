# dd-continuous-profiler-dash2025

Example service used for the [_Read Between the Stacktraces: Investigations with Continuous Profiler_](https://www.dashcon.io/sessions/read-between-the-stacktraces-investigations-with-continuous-profiler/) workshop and the Continuous Profiler course on the Datadog Learning Center.

## Pre-requisites
1. Install Docker
2. Install docker-compose
3. Install Java

## Quick Start
* Run `docker-compose up` in the root directory to start up mongodb
* Run `./gradlew run` in a separate terminal tab to run the server (will stay at 75% done, that's expected)
* Run `curl http://localhost:8081/movies?q=jurassic` to query the movies endpoint, should get a JSON response
