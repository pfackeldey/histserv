#!/usr/bin/env bash

action() {
    # DEBUG logging is useful for local development, but should not be used in production.
    histserv --port 50051 --log-level DEBUG
}
action "$@"
