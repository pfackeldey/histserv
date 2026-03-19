#!/usr/bin/env bash

action() {
    histserv --port 50051 --n-threads 4
}
action "$@"
