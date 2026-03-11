#!/usr/bin/env bash

action() {
    haas-server --port 50051 --n-threads 4
}
action "$@"
